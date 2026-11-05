"""Stream frames through the existing detector, then encode browser-safe MP4."""

from __future__ import annotations

import math
import shutil
import subprocess
import time
import json
from pathlib import Path

import cv2

from .config import MAX_VIDEO_FRAMES, MAX_VIDEO_SECONDS
from .model_service import ModelService


def ffmpeg_executable() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        from imageio_ffmpeg import get_ffmpeg_exe
        return get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


def inspect_video(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("This video cannot be opened")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        estimated_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ok, frame = cap.read()
        if not ok or frame is None or frame.size == 0:
            raise ValueError("This video has no decodable frames")
        if not math.isfinite(fps) or not 0 < fps <= 120:
            raise ValueError("The video frame rate is missing or unsupported")
        if width < 1 or height < 1 or width * height > 50_000_000:
            raise ValueError("The video resolution is unsupported")
        duration = estimated_frames / fps if estimated_frames > 0 else None
        if duration is not None and duration > MAX_VIDEO_SECONDS:
            raise ValueError(f"Video is longer than the {MAX_VIDEO_SECONDS}-second limit")
        if estimated_frames > MAX_VIDEO_FRAMES:
            raise ValueError(f"Video exceeds the {MAX_VIDEO_FRAMES}-frame limit")
        return {"width": width, "height": height, "fps": round(fps, 4),
                "estimated_total_frames": estimated_frames or None,
                "duration_seconds": round(duration, 2) if duration is not None else None}
    finally:
        cap.release()


def _has_audio(ffmpeg: str, source: Path) -> bool:
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(source), "-t", "0",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=30,
                           errors="replace")
    return "Audio:" in probe.stderr


def process_video(source: Path, output: Path, model: ModelService,
                  confidence: float, iou: float, metadata: dict, progress, encoding_started) -> dict:
    ffmpeg = ffmpeg_executable()
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required for browser-compatible video output")
    temp_video = output.with_name("video_uncompressed_intermediate.mp4")
    cap = cv2.VideoCapture(str(source))
    writer = cv2.VideoWriter(str(temp_video), cv2.VideoWriter_fourcc(*"mp4v"),
                             metadata["fps"], (metadata["width"], metadata["height"]))
    if not cap.isOpened() or not writer.isOpened():
        cap.release()
        writer.release()
        raise RuntimeError("Video decoder or encoder could not be opened")
    start = time.perf_counter()
    count = instances = frames_with_detections = 0
    inference_ms = 0.0
    classes: set[str] = set()
    timeline = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if count >= MAX_VIDEO_FRAMES or count / metadata["fps"] >= MAX_VIDEO_SECONDS:
                raise RuntimeError("Video exceeded the processing limit while decoding")
            annotated, detections, elapsed_ms = model.predict(frame, confidence, iou)
            writer.write(annotated)
            count += 1
            instances += len(detections)
            frames_with_detections += bool(detections)
            inference_ms += elapsed_ms
            classes.update(item["class_name"] for item in detections)
            timeline.append({"frame": count-1, "seconds": round((count-1)/metadata["fps"], 4), "count": len(detections), "detections": detections})
            progress(count)
        if count == 0:
            raise RuntimeError("No decodable video frames were found")
    except Exception:
        temp_video.unlink(missing_ok=True)
        raise
    finally:
        cap.release()
        writer.release()
    encoding_started()
    output.with_suffix(".timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    has_audio = _has_audio(ffmpeg, source)
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(temp_video),
               "-i", str(source), "-map", "0:v:0", "-map", "1:a?", "-c:v", "libx264",
               "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags",
               "+faststart", "-shortest", str(output)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=600, errors="replace")
        if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("Browser-compatible MP4 encoding failed")
    finally:
        temp_video.unlink(missing_ok=True)
    return {"frames_processed": count, "duration_seconds": round(count / metadata["fps"], 2),
            "width": metadata["width"], "height": metadata["height"], "fps": metadata["fps"],
            "frames_with_detections": frames_with_detections,
            "frame_level_detection_instances": instances,
            "timeline": [{"frame": r["frame"], "seconds": r["seconds"], "count": r["count"]} for r in timeline],
            "detected_classes": sorted(classes),
            "average_model_call_ms": round(inference_ms / count, 2),
            "total_processing_seconds": round(time.perf_counter() - start, 2),
            "audio": "AAC audio included" if has_audio else "Source contains no audio stream"}
