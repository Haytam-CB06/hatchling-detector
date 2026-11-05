"""Integrated local lifecycle API. User choices are validated; source files stay immutable."""
from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import config
from .platform_data import IMAGE_EXTENSIONS, list_images, preparation_preflight
from .platform_db import PlatformDB, digest, now, uid
from .platform_jobs import Jobs, hardware, public_model, read_metrics, train_preflight


class GroupInput(BaseModel):
    group_id: str = Field(min_length=2, max_length=160)
    split: Literal["unassigned", "train", "val", "test"] = "unassigned"
    confirmed: bool = False
    independent: bool = False
    reviewer: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=3, max_length=2000)


class PreparationInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    image_ids: list[str] = Field(min_length=1, max_length=5000)


class TrainingInput(BaseModel):
    version_id: str
    model_id: str
    epochs: int = 50
    imgsz: int = 640
    batch: int = 4
    lr0: float = .001
    optimizer: str = "AdamW"
    device: str = "cpu"
    patience: int = 20
    seed: int = 42
    mosaic: float = .5
    max_hours: float = 1
    confirm_resources: bool = False


class EvaluationInput(BaseModel):
    model_id: str
    version_id: str
    split: Literal["val", "test"] = "val"
    device: str = "cpu"
    imgsz: int = Field(default=640, ge=128, le=2048)
    confidence: float = Field(default=.25, ge=.01, le=.99)
    iou: float = Field(default=.45, ge=.01, le=.99)


def safe_relative(value):
    value = value.replace("\\", "/")
    path = PurePosixPath(value)
    if not value or not path.parts or path.is_absolute() or any(part in {".", "..", ""} or ":" in part or "\x00" in part for part in path.parts):
        raise HTTPException(422, "Unsafe relative file path")
    if len(value) > 200 or any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", part) for part in path.parts):
        raise HTTPException(422, "File path is unsupported on Windows")
    return path


def extract_zip(source: Path, destination: Path):
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        expanded=sum(m.file_size for m in members)
        if expanded>max(0,shutil.disk_usage(source.parent).free-128_000_000):
            raise HTTPException(413,'Insufficient project storage for the expanded archive')
        if len(members) > 10000 or expanded > 2_000_000_000:
            raise HTTPException(413, "Archive exceeds 10,000 files or 2 GB expanded size")
        for member in members:
            relative = safe_relative(member.filename.rstrip("/"))
            if stat.S_ISLNK(member.external_attr >> 16) or member.file_size > 250_000_000:
                raise HTTPException(422, "Archive links and oversized members are not allowed")
            target = destination.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise HTTPException(422, "Archive path escaped the import")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise HTTPException(422, "Archive has duplicate file paths")
            with archive.open(member) as src, target.open("xb") as out:
                shutil.copyfileobj(src, out, 1024 * 1024)


class Platform:
    def __init__(self, review, model, inference_jobs, executor, root=None):
        self.review, self.model, self.inference_jobs, self.executor = review, model, inference_jobs, executor
        self.db = PlatformDB(review.db, root or config.PLATFORM_ROOT)
        self.jobs = Jobs(self.db)

    def bootstrap(self):
        if not self.db.one("SELECT id FROM platform_datasets WHERE id='frozen-evaluation'") or not self.db.one("SELECT id FROM platform_models"):
            if self.db.one("SELECT id FROM platform_jobs WHERE kind='bootstrap' AND status IN ('queued','running')"):
                return
            return self.jobs.create("bootstrap", {})

    def overview(self):
        images = list_images(self.db)
        status = {}
        objects = 0
        issues = []
        for image in images:
            status[image["status"]] = status.get(image["status"], 0)+1
            if image["status"] in {"verified_positive", "verified_negative"}:
                objects += sum(b["class_name"] == "hatchling" for b in image["boxes"])
            issues.extend({**issue, "image_id": image["id"], "filename": image["filename"], "resolved_by_review": image["status"] in {"verified_positive", "verified_negative"}} for issue in image["issues"])
        active = self.db.one("SELECT value FROM platform_settings WHERE key='active_model'")
        model = public_model(self.db.one("SELECT * FROM platform_models WHERE id=?", (active["value"],))) if active else None
        jobs = [self.jobs.get(row["id"]) for row in self.db.all("SELECT id FROM platform_jobs ORDER BY created_at DESC LIMIT 12")]
        inference = self.inference_jobs.history()
        active_sha = model['sha256'] if model else self.model.info().get('sha256')
        speeds = [j["stats"]["model_call_ms"] for j in inference if j.get('model_sha256')==active_sha and j.get("stats") and "model_call_ms" in j["stats"]]
        return {"active_model": model, "model_state": self.model.info(), "datasets": self.db.one("SELECT COUNT(*) n FROM platform_datasets")["n"],
                "images": len(images), "approved_objects": objects, "review_status": status,
                "pending_reviews": sum(v for k, v in status.items() if k in {"unreviewed", "in_review", "ambiguous", "needs_correction"}),
                "source_annotated_objects": sum(len(i["original"]) for i in images), "quality_issues": issues[:100],
                "quality_issue_count": len(issues), "jobs": jobs, "hardware": hardware(),
                "inference_average_ms": sum(speeds)/len(speeds) if speeds else None,
                "inference_sample_count": len(speeds), "versions": self.db.one("SELECT COUNT(*) n FROM platform_versions")["n"]}


def create_platform_router(platform: Platform):
    p = platform; db = p.db
    router = APIRouter(prefix="/api/platform", tags=["model lifecycle"])

    def found(table, identifier):
        # The table argument is a constant supplied by this module, never user input.
        row = db.one(f"SELECT * FROM {table} WHERE id=?", (identifier,))
        if not row: raise HTTPException(404, "Record not found")
        return row

    def create_job(kind, payload):
        try: return p.jobs.create(kind, payload)
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc

    @router.get("/overview")
    def overview(): return p.overview()

    @router.get("/hardware")
    def resources(): return hardware()

    @router.get("/datasets")
    def datasets():
        rows = db.all("SELECT * FROM platform_datasets ORDER BY created_at DESC")
        for row in rows:
            row["classes"] = json.loads(row.pop("classes_json")); row["summary"] = json.loads(row.pop("summary_json")); row.pop("root_path")
            image_rows = db.all("SELECT i.id,r.status FROM platform_images i LEFT JOIN reviews r ON r.image_id=i.id WHERE dataset_id=?", (row["id"],))
            row["images"] = len(image_rows); row["approved"] = sum(r["status"] in {"verified_positive", "verified_negative"} for r in image_rows)
            row["training_eligible"] = row["pool"] == "training" and row["approved"] > 0
        return rows

    @router.get("/datasets/{dataset_id}")
    def dataset(dataset_id: str):
        record = found("platform_datasets", dataset_id)
        return {"dataset": {k: v for k, v in record.items() if k != "root_path"}, "images": list_images(db, dataset_id)}

    @router.post("/datasets/upload", status_code=202)
    async def upload(files: list[UploadFile] = File(...), name: str = Form(...), source: str = Form("User upload"),
                     pool: Literal["training", "evaluation"] = Form("training"), classes: str = Form('{"0":"hatchling"}'), paths: str = Form("[]"),frame_stride:int=Form(30),max_frames:int=Form(200)):
        if not name.strip() or len(name) > 100 or len(source) > 2000: raise HTTPException(422, "Provide a dataset name and bounded source description")
        try:
            class_map = json.loads(classes); relative_paths = json.loads(paths)
            if isinstance(class_map, list): class_map = dict(enumerate(class_map))
            if not class_map or not isinstance(class_map, dict) or any(not str(k).isdigit() or not isinstance(v, str) for k, v in class_map.items()): raise ValueError()
            if relative_paths and len(relative_paths) != len(files): raise ValueError()
        except (ValueError, TypeError): raise HTTPException(422, "Class names or folder paths are invalid")
        if len(files) > 10000: raise HTTPException(413, "At most 10,000 upload files per import")
        if not 1<=frame_stride<=3000 or not 1<=max_frames<=500:raise HTTPException(422,'Frame stride must be 1–3000 and extraction count 1–500')
        upload_limit=min(1_000_000_000,max(0,shutil.disk_usage(db.root).free-128_000_000))
        dataset_id = uid(); folder = db.root / "imports" / dataset_id; raw = folder / "raw"; raw.mkdir(parents=True)
        total = 0
        try:
            for index, file in enumerate(files):
                relative = safe_relative(relative_paths[index] if relative_paths else file.filename or "unnamed")
                target = raw.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists(): raise HTTPException(422, "Duplicate upload paths")
                with target.open("xb") as stream:
                    while chunk := await file.read(1024 * 1024):
                        total += len(chunk)
                        if total > upload_limit: raise HTTPException(413, "Import exceeds the available storage or 1 GB upload limit")
                        stream.write(chunk)
                if target.suffix.lower() == ".zip":
                    extract_zip(target, raw / (target.stem + "_contents"))
            db.execute("INSERT INTO platform_datasets VALUES(?,?,?,?,?,?,?,?,?,?)", (dataset_id, name.strip(), dataset_id[:12], source, pool, now(), "queued", str(raw), json.dumps(class_map), '{}'))
        except (zipfile.BadZipFile, OSError) as exc:
            raise HTTPException(422, f"Import could not be staged: {exc}") from exc
        videos = [file for file in raw.rglob("*") if file.suffix.lower() in config.VIDEO_EXTENSIONS]
        if videos and not any(file.suffix.lower() in IMAGE_EXTENSIONS for file in raw.rglob("*")):
            if len(videos) != 1: raise HTTPException(422, "Upload one source video per extraction dataset")
            job = create_job("extract_frames", {"dataset_id": dataset_id, "filename": videos[0].relative_to(raw).as_posix(), "stride": frame_stride, "max_frames": max_frames})
        else:
            job = create_job("inspect", {"dataset_id": dataset_id})
        return {"dataset_id": dataset_id, "job": job}

    @router.post("/datasets/{dataset_id}/inspect")
    def inspect(dataset_id: str):
        found("platform_datasets", dataset_id)
        return create_job("inspect", {"dataset_id": dataset_id})

    @router.post("/datasets/{dataset_id}/approve")
    def approve_dataset(dataset_id: str):
        found("platform_datasets",dataset_id)
        images = list_images(db,dataset_id)
        pending = [i for i in images if i['status'] not in {'verified_positive','verified_negative','rejected','excluded'}]
        approved = [i for i in images if i['status'] in {'verified_positive','verified_negative'}]
        if pending or not approved: raise HTTPException(422,f"{len(pending)} images still need a final decision; {len(approved)} approved samples available")
        db.execute("UPDATE platform_datasets SET state='approved' WHERE id=?",(dataset_id,))
        db.event('dataset_approved',dataset_id,{'approved':len(approved),'excluded':len(images)-len(approved)})
        return {'approved':len(approved),'excluded':len(images)-len(approved)}

    @router.post("/datasets/{dataset_id}/suggest", status_code=202)
    def suggest(dataset_id: str, payload: dict):
        found("platform_datasets", dataset_id); found("platform_models", str(payload.get("model_id", "")))
        return create_job("suggest", {"dataset_id": dataset_id, "model_id": payload["model_id"]})

    @router.get("/quality")
    def quality():
        return [{"id": i["id"], "filename": i["filename"], "dataset_id": i["dataset_id"], "status": i["status"], "issues": i["issues"], "image_url": i["image_url"]}
                for i in list_images(db) if i["issues"]]

    @router.put("/images/{image_id}/group")
    def group(image_id: str, body: GroupInput):
        image = found("platform_images", image_id)
        if image["pool"] == "evaluation" and body.split in {"train", "val"}:
            raise HTTPException(422, "Frozen evaluation images cannot enter training or validation")
        if not body.reviewer.strip() or not body.evidence.strip(): raise HTTPException(422, "Reviewer and source evidence required")
        if body.confirmed and body.group_id.startswith(('unknown:','image:','file:')):
            raise HTTPException(422,"Replace the image/file placeholder with a confirmed recording or wildlife-event group")
        db.execute("INSERT INTO platform_groups VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(image_id) DO UPDATE SET group_id=excluded.group_id,split=excluded.split,confirmed=excluded.confirmed,reviewer=excluded.reviewer,evidence=excluded.evidence,independent=excluded.independent,updated_at=excluded.updated_at",
                   (image_id, body.group_id.strip(), body.split, int(body.confirmed), body.reviewer.strip(), body.evidence.strip(), int(body.independent), now()))
        db.event("group_assignment", image_id, body.model_dump())
        return body.model_dump()

    @router.put("/images/{image_id}/quality")
    def quality_decision(image_id: str, payload: dict):
        image=found('platform_images',image_id)
        if payload.get('code')!='suspected_frozen_overlap' or payload.get('decision') not in {'distinct_source_confirmed','uncertain'}:
            raise HTTPException(422,'Only a suspected perceptual overlap can be adjudicated; exact frozen matches stay protected')
        reviewer=str(payload.get('reviewer','')).strip(); evidence=str(payload.get('evidence','')).strip()
        if not reviewer or len(evidence)<10 or len(evidence)>2000: raise HTTPException(422,'Reviewer and detailed source evidence are required')
        db.execute('INSERT INTO platform_quality_decisions VALUES(?,?,?,?,?,?) ON CONFLICT(image_id,code) DO UPDATE SET reviewer=excluded.reviewer,evidence=excluded.evidence,decision=excluded.decision,created_at=excluded.created_at',(image_id,payload['code'],reviewer,evidence,payload['decision'],now()))
        db.event('quality_adjudication',image_id,{'source_sha256':image['sha256'],**payload})
        return {'saved':True}

    @router.post("/prepare/preflight")
    def preflight(body: PreparationInput):
        p.review.refresh()
        result = preparation_preflight(db, p.review, body.image_ids); result.pop("selected")
        return result

    @router.post("/prepare", status_code=202)
    def prepare(body: PreparationInput):
        check = preflight(body)
        if not check["ready"]: raise HTTPException(422, check)
        return create_job("prepare", body.model_dump())

    @router.get("/versions")
    def versions():
        rows = db.all("SELECT * FROM platform_versions ORDER BY created_at DESC")
        for row in rows:
            row["manifest"] = json.loads(row.pop("manifest_json")); row["summary"] = json.loads(row.pop("summary_json")); row.pop("path")
        return rows

    @router.get("/versions/{version_id}/download")
    def version_download(version_id: str):
        row = found("platform_versions", version_id)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in Path(row["path"]).rglob("*"):
                if file.is_file(): archive.write(file, file.relative_to(row["path"]).as_posix())
        stream.seek(0)
        return StreamingResponse(stream, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="nazar-{version_id[:12]}.zip"'})

    @router.get("/jobs")
    def jobs(): return [p.jobs.get(row["id"]) for row in db.all("SELECT id FROM platform_jobs ORDER BY created_at DESC LIMIT 200")]

    @router.get("/jobs/{job_id}")
    def job(job_id: str):
        record = p.jobs.get(job_id)
        if not record: raise HTTPException(404, "Job not found")
        metrics_path = db.root / "experiments" / job_id / "results.csv"
        record["metrics"], _ = read_metrics(metrics_path)
        return record

    @router.get("/jobs/{job_id}/logs")
    def logs(job_id: str):
        record = found("platform_jobs", job_id)
        file = Path(record["log_path"])
        text = file.read_text(encoding="utf-8", errors="replace")[-64000:] if file.is_file() else ""
        return {"text": text, "truncated": file.stat().st_size > 64000 if file.is_file() else False}

    @router.post("/jobs/{job_id}/stop")
    def stop(job_id: str):
        found("platform_jobs", job_id)
        p.jobs.update(job_id, cancel_requested=1)
        return {"message": "Stop requested; training stops after the current epoch and preserves checkpoints"}

    @router.post("/jobs/{job_id}/retry")
    def retry(job_id: str):
        record = p.jobs.get(job_id)
        if not record or record["status"] not in {"failed", "stopped", "interrupted"} or record["kind"] not in {"inspect", "bootstrap", "report", "registry_scan"}:
            raise HTTPException(422, "This job is not safely retryable; create a new experiment instead")
        return create_job(record["kind"], record["payload"])

    @router.post("/training/preflight")
    def training_check(body: TrainingInput): return train_preflight(db, body.model_dump())

    @router.post("/training/start", status_code=202)
    def training(body: TrainingInput):
        check = training_check(body)
        if not check["ready"]: raise HTTPException(422, check)
        return create_job("train", body.model_dump())

    @router.post("/jobs/{job_id}/resume", status_code=202)
    def resume(job_id: str):
        previous = p.jobs.get(job_id)
        if not previous or previous["kind"] != "train" or previous["status"] not in {"stopped", "interrupted", "failed"}:
            raise HTTPException(422, "Only interrupted or stopped training jobs can resume")
        payload = previous["payload"]; payload["resume_job_id"] = job_id
        check = train_preflight(db, payload)
        if not check["ready"]: raise HTTPException(422, check)
        return create_job("train", payload)

    @router.get("/models")
    def models():
        setting = db.one("SELECT value FROM platform_settings WHERE key='active_model'")
        return [{**public_model(row), "active": bool(setting and row["id"] == setting["value"])} for row in db.all("SELECT * FROM platform_models ORDER BY created_at DESC")]

    @router.get("/models/{model_id}/history")
    def model_history(model_id: str):
        row = found("platform_models", model_id)
        rows, _ = read_metrics((config.ROOT / row["checkpoint"]).parent.parent / "results.csv")
        return rows

    @router.post("/models/scan", status_code=202)
    def model_scan(): return create_job("registry_scan", {})

    @router.post("/models/{model_id}/activate")
    async def activate(model_id: str):
        row = found("platform_models", model_id)
        if row["pretrained"]: raise HTTPException(422, "Pretrained weights initialize experiments; activate a trained hatchling detector")
        path = config.ROOT / row["checkpoint"]
        if digest(path) != row["sha256"]: raise HTTPException(409, "Checkpoint hash changed")
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(p.executor, p.model.activate, path, row["sha256"])
        except Exception as exc: raise HTTPException(422, f"Activation failed: {exc}") from exc
        db.execute("INSERT INTO platform_settings VALUES('active_model',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (model_id,))
        db.event("model_activated", model_id, {"sha256": row["sha256"]})
        return p.model.info()

    @router.get("/models/{model_id}/download")
    def download_model(model_id: str):
        row = found("platform_models", model_id)
        return FileResponse(config.ROOT / row["checkpoint"], filename=f"nazar-{model_id[:12]}.pt")

    @router.post("/evaluation/start", status_code=202)
    def evaluate(body: EvaluationInput):
        version = found("platform_versions", body.version_id); selected_model=found("platform_models", body.model_id)
        if selected_model['pretrained']:raise HTTPException(422,'Select a trained hatchling detector for evaluation')
        entries = [row for row in json.loads(version["manifest_json"]) if row["split"] == body.split]
        if not entries: raise HTTPException(422, "No verified images in the selected partition")
        if not any(any(b['class_name']=='hatchling' for b in row['boxes']) for row in entries):
            raise HTTPException(422,'This is a verified negative-only partition; full recall/mAP evaluation requires at least one annotated hatchling')
        if body.device not in hardware()["devices"]: raise HTTPException(422, "Device unavailable")
        if body.split == "test" and any(row["pool"] == "evaluation" for row in entries):
            if body.confidence != .25 or body.iou != .45:
                raise HTTPException(422, "Frozen test uses the predeclared deployment thresholds 0.25 / 0.45; use validation for threshold exploration")
        return create_job("evaluate", body.model_dump())

    @router.get("/evaluations")
    def evaluations():
        rows = db.all("SELECT * FROM platform_evaluations ORDER BY created_at DESC")
        for row in rows:
            row["result"] = json.loads(row.pop("result_json")); row["settings"] = json.loads(row.pop("settings_json")); row.pop("path")
        return rows

    @router.get("/evaluations/{evaluation_id}/files/{filename}")
    def evaluation_file(evaluation_id: str, filename: str):
        row = found("platform_evaluations", evaluation_id)
        if Path(filename).name != filename or Path(filename).suffix not in {".png", ".jpg", ".json"}: raise HTTPException(422, "Unsupported artifact")
        path = Path(row["path"]) / filename
        if not path.is_file(): raise HTTPException(404, "Artifact not found")
        return FileResponse(path)

    @router.get("/inference")
    def inference_history(): return p.inference_jobs.history()

    @router.post("/active-learning/candidates", status_code=202)
    def candidate(payload: dict):
        job_id = str(payload.get("job_id", ""))
        job = p.inference_jobs.get(job_id)
        if not job or job["status"] != "completed": raise HTTPException(422, "Select a completed inference job")
        folder = p.inference_jobs.root / job_id
        original = next(iter(folder.glob("upload.*")), None)
        if original is None: raise HTTPException(410, "Original upload expired; upload the media as a dataset")
        dataset_id = uid(); raw = db.root / "imports" / dataset_id / "raw"; raw.mkdir(parents=True)
        target = raw / original.name; shutil.copyfile(original, target)
        (raw.parent/'inference_context.json').write_text(json.dumps({'job_id':job_id,'model_sha256':job.get('model_sha256'),'settings':job.get('settings',{})}),encoding='utf-8')
        db.execute("INSERT INTO platform_datasets VALUES(?,?,?,?,?,?,?,?,?,?)", (dataset_id, str(payload.get("name", "Inference review candidates"))[:100], dataset_id[:12], f"Inference job {job_id}; predictions are unverified", "training", now(), "queued", str(raw), '{"0":"hatchling"}', '{}'))
        if job["kind"] == "video":
            timeline=folder/'annotated.timeline.json'
            if timeline.is_file():shutil.copyfile(timeline,raw.parent/'source_frame_predictions.json')
            result = create_job("extract_frames", {"dataset_id": dataset_id, "filename": target.name, "stride": 30, "max_frames": 200})
        else:
            # Preserve the predictions as provenance without approving them.
            (raw.parent / "prediction_suggestions.json").write_text(json.dumps(job.get("detections", [])), encoding="utf-8")
            result = create_job("inspect", {"dataset_id": dataset_id})
        return {"dataset_id": dataset_id, "job": result}

    @router.get("/monitoring")
    def monitoring(): return {"camera_available": False, "camera_message": "No live-camera backend is configured. Uploaded-video analysis is available.",
                              "videos": [job for job in p.inference_jobs.history() if job["kind"] == "video"]}

    @router.get("/reports")
    def reports():
        return [{k: v for k, v in row.items() if k != "path"} for row in db.all("SELECT * FROM platform_reports ORDER BY created_at DESC")]

    @router.post("/reports", status_code=202)
    def report(payload: dict):
        if payload.get("kind") not in {"project", "dataset", "annotations", "preparation", "training", "models", "evaluation", "comparison", "inference"}:
            raise HTTPException(422, "Unsupported report kind")
        return create_job("report", {"kind": payload["kind"], "entity_id": payload.get("entity_id")})

    @router.get("/reports/{report_id}/{format}")
    def report_download(report_id: str, format: Literal["pdf", "csv", "json"]):
        row = found("platform_reports", report_id)
        return FileResponse(Path(row["path"]) / f"report.{format}", filename=f"nazar-{row['kind']}-{report_id[:8]}.{format}")

    @router.get("/history")
    def history(): return db.all("SELECT * FROM platform_events ORDER BY created_at DESC LIMIT 200")

    @router.get("/evidence/{task}")
    def evidence(task: Literal["task01", "task02", "task03"]):
        paths = {"task01": "artifacts/model_improvement/task01_audit/REPORT.md", "task02": "artifacts/model_improvement/task02_error_analysis/REPORT.md", "task03": "artifacts/model_improvement/task03_annotation_validation/REPORT.md"}
        return FileResponse(config.ROOT / paths[task], filename=f"nazar-{task}-evidence.md")

    return router
