"""Nazar Vision Detection Studio API."""

from __future__ import annotations

import asyncio
import shutil
import threading
import time
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

import cv2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from . import config
from .model_service import ModelService
from .review import ReviewStore, create_review_router
from .platform_api import Platform, create_platform_router
from .storage import cleanup_old_jobs, new_job_dir, store_upload
from .video_service import ffmpeg_executable, inspect_video, process_video


class JobStore:
    def __init__(self, root: Path):
        self.root = root
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.history_root = root.parent / "inference_history"
        self.history_root.mkdir(parents=True, exist_ok=True)
        for file in root.glob("*/state.json"):
            try:
                record = json.loads(file.read_text(encoding="utf-8"))
                if record["status"] in {"queued", "processing"}:
                    record.update(status="failed", error="API restarted during inference; submit the preserved source again")
                self._jobs[record["job_id"]] = record
            except (OSError, ValueError, KeyError):
                continue

    def _persist(self, job_id):
        record = self._jobs[job_id]
        folder = self.root / job_id
        if folder.exists():
            (folder / "state.json").write_text(json.dumps(record, default=str), encoding="utf-8")
        (self.history_root / f"{job_id}.json").write_text(json.dumps(record, default=str), encoding="utf-8")

    def history(self):
        records = []
        for file in self.history_root.glob("*.json"):
            try:
                row = json.loads(file.read_text(encoding="utf-8"))
                records.append({k: v for k, v in row.items() if k != "output_path"})
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda row: row["created_at"], reverse=True)[:200]

    def add(self, job_id: str, kind: str, estimated_frames: int | None = None) -> None:
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id, "kind": kind, "status": "queued", "created_at": time.time(),
                "stage": "queued",
                "processed_frames": 0, "estimated_total_frames": estimated_frames,
                "stats": None, "detections": None, "error": None,
                "result_url": None, "download_url": None, "output_path": None,
            }
            self._persist(job_id)

    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(changes)
                if "processed_frames" not in changes or changes["processed_frames"] % 10 == 0 or changes.get("status") == "completed":
                    self._persist(job_id)

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            public = {k: v for k, v in job.items() if k not in {"created_at", "output_path"}}
            estimated = public["estimated_total_frames"]
            public["progress_percent"] = (
                100 if public["status"] == "completed" else
                min(100, round(public["processed_frames"] / estimated * 100))
                if estimated and public["status"] == "processing" else None
            )
            return public

    def output(self, job_id: str) -> Path | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return Path(job["output_path"]) if job and job["status"] == "completed" and job.get("output_path") else None

    def expire(self) -> None:
        cutoff = time.time() - config.JOB_TTL_SECONDS
        with self._lock:
            expired = [key for key, job in self._jobs.items() if job["created_at"] < cutoff]
            for key in expired:
                self._jobs.pop(key)
            active = set(self._jobs)
        for key in expired:
            shutil.rmtree(self.root / key, ignore_errors=True)
        cleanup_old_jobs(self.root, active)


def _image_metadata(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as image:
            width, height = image.size
            if width * height > config.MAX_IMAGE_PIXELS:
                raise HTTPException(413, "Image resolution exceeds the 50-megapixel limit")
            image.verify()
            if image.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Unsupported image content")
            return width, height
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "The image is corrupt or its content is unsupported") from None


def _run_image(source: Path, output: Path, model: ModelService,
               confidence: float, iou: float) -> tuple[list[dict], dict]:
    frame = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("The image could not be decoded")
    start = time.perf_counter()
    annotated, detections, model_ms = model.predict(frame, confidence, iou)
    if not cv2.imwrite(str(output), annotated):
        raise RuntimeError("Annotated image could not be saved")
    stats = {"object_count": len(detections),
             "detected_classes": sorted({d["class_name"] for d in detections}),
             "model_call_ms": model_ms,
             "total_processing_ms": round((time.perf_counter() - start) * 1000, 2),
             "width": int(frame.shape[1]), "height": int(frame.shape[0])}
    return detections, stats


def _video_worker(store: JobStore, job_id: str, source: Path, output: Path,
                  model: ModelService, confidence: float, iou: float, metadata: dict) -> None:
    store.update(job_id, status="processing", stage="inference")
    try:
        stats = process_video(source, output, model, confidence, iou, metadata,
                              lambda count: store.update(job_id, processed_frames=count),
                              lambda: store.update(job_id, stage="encoding"))
        store.update(job_id, status="completed", stage="completed", stats=stats, processed_frames=stats["frames_processed"],
                     output_path=output, result_url=f"/api/jobs/{job_id}/result",
                     download_url=f"/api/jobs/{job_id}/result?download=1")
    except Exception:
        output.unlink(missing_ok=True)
        store.update(job_id, status="failed", stage="failed", error="Video processing failed. Check that the media can be decoded and encoded.")
    finally:
        pass  # The uploaded copy is retained for human-review candidate creation until normal expiry.


def create_app(model_path: Path | None = None, job_root: Path | None = None,
               review_manifest: Path | None = None, review_predictions: Path | None = None,
               review_db: Path | None = None, review_exports: Path | None = None,
               platform_root: Path | None = None, bootstrap_platform: bool = True) -> FastAPI:
    model = ModelService(model_path or config.MODEL_PATH, config.DEVICE, config.IMAGE_SIZE)
    root = job_root or config.JOB_ROOT
    store = JobStore(root)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nazar-inference")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        root.mkdir(parents=True, exist_ok=True)
        store.expire()
        loop = asyncio.get_running_loop()
        loading = loop.run_in_executor(executor, model.load)
        app.state.loading = loading
        if bootstrap_platform:
            platform.bootstrap()
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Nazar Vision — Model Lifecycle Platform", version="2.0.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5050, 5173)],
                       allow_credentials=False, allow_methods=["GET", "POST", "PUT"], allow_headers=["*"])
    review_store = ReviewStore(
        review_manifest or config.REVIEW_MANIFEST,
        review_predictions or config.REVIEW_PREDICTIONS,
        review_db or config.REVIEW_DB,
        review_exports or config.REVIEW_EXPORTS,
        config.REVIEW_TRAIN_MANIFEST,
        config.REVIEW_TRAIN_PREDICTIONS,
    )
    app.include_router(create_review_router(review_store))
    platform = Platform(review_store, model, store, executor, platform_root)
    selected = platform.db.one("SELECT m.checkpoint,m.sha256 FROM platform_models m JOIN platform_settings s ON m.id=s.value WHERE s.key='active_model'")
    if selected and model_path is None:
        model.path = config.ROOT / selected["checkpoint"]
        model.expected_sha = selected['sha256']
    app.include_router(create_platform_router(platform))
    app.state.platform = platform
    app.state.model_service = model
    app.state.jobs = store

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model_state": model.info()["state"],
                "video_encoding_ready": ffmpeg_executable() is not None}

    @app.get("/api/model/info")
    def model_info():
        return model.info()

    @app.post("/api/detect/image")
    async def detect_image(file: UploadFile = File(...), confidence: float = Form(0.25), iou: float = Form(0.45)):
        if not 0.01 <= confidence <= 0.99 or not 0.01 <= iou <= 0.99:
            raise HTTPException(422, "Confidence and IoU must be between 0.01 and 0.99")
        if model.info()["state"] != "ready":
            raise HTTPException(503, "Model is not ready")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in config.IMAGE_EXTENSIONS:
            raise HTTPException(415, "Supported images: JPG, JPEG, PNG, WEBP")
        store.expire()
        job_id, folder = new_job_dir(root)
        source, output = folder / f"upload{suffix}", folder / "annotated.png"
        try:
            await store_upload(file, source, config.MAX_IMAGE_BYTES)
            width, height = _image_metadata(source)
            store.add(job_id, "image")
            loop = asyncio.get_running_loop()
            detections, stats = await loop.run_in_executor(
                executor, _run_image, source, output, model, confidence, iou)
            stats.update({"width": width, "height": height})
            store.update(job_id, status="completed", stage="completed", detections=detections, stats=stats,
                         model_sha256=model.info()["sha256"], settings={"confidence": confidence, "iou": iou},
                         output_path=output, result_url=f"/api/jobs/{job_id}/result",
                         download_url=f"/api/jobs/{job_id}/result?download=1")
            return store.get(job_id)
        except HTTPException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise HTTPException(500, "Image inference failed") from None

    @app.post("/api/detect/video", status_code=202)
    async def detect_video(file: UploadFile = File(...), confidence: float = Form(0.25), iou: float = Form(0.45)):
        if not 0.01 <= confidence <= 0.99 or not 0.01 <= iou <= 0.99:
            raise HTTPException(422, "Confidence and IoU must be between 0.01 and 0.99")
        if model.info()["state"] != "ready":
            raise HTTPException(503, "Model is not ready")
        if ffmpeg_executable() is None:
            raise HTTPException(503, "Video encoding is unavailable; install backend requirements")
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in config.VIDEO_EXTENSIONS:
            raise HTTPException(415, "Supported videos: MP4, MOV, AVI")
        store.expire()
        job_id, folder = new_job_dir(root)
        source, output = folder / f"upload{suffix}", folder / "annotated.mp4"
        try:
            await store_upload(file, source, config.MAX_VIDEO_BYTES)
            metadata = inspect_video(source)
            store.add(job_id, "video", metadata["estimated_total_frames"])
            store.update(job_id, model_sha256=model.info()["sha256"], settings={"confidence": confidence, "iou": iou})
            loop = asyncio.get_running_loop()
            future = loop.run_in_executor(executor, _video_worker, store, job_id, source, output,
                                          model, confidence, iou, metadata)
            app.state.last_video_future = future
            response = store.get(job_id)
            response["source_metadata"] = metadata
            return response
        except ValueError as exc:
            shutil.rmtree(folder, ignore_errors=True)
            raise HTTPException(400, str(exc)) from None
        except HTTPException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise HTTPException(500, "Video upload failed") from None

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found or expired")
        return job

    @app.get("/api/jobs/{job_id}/result")
    def get_result(job_id: str, download: bool = False):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(404, "Job not found or expired")
        if job["status"] != "completed":
            raise HTTPException(409, "The result is not ready")
        path = store.output(job_id)
        if path is None or not path.is_file():
            raise HTTPException(410, "The result has expired")
        media_type = "image/png" if job["kind"] == "image" else "video/mp4"
        return FileResponse(path, media_type=media_type,
                            filename=f"nazar-vision-{job_id}{path.suffix}" if download else None,
                            content_disposition_type="attachment" if download else "inline")

    return app


app = create_app()
