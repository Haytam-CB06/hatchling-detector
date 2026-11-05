"""Bounded uploads and per-job files; user filenames never become server paths."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from .config import JOB_TTL_SECONDS


def new_job_dir(root: Path) -> tuple[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    job_id = uuid4().hex
    path = root / job_id
    path.mkdir(mode=0o700)
    return job_id, path


async def store_upload(upload: UploadFile, destination: Path, limit: int) -> int:
    total = 0
    try:
        with destination.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {limit // (1024 * 1024)} MB limit")
                handle.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    if total == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    return total


def cleanup_old_jobs(root: Path, active_ids: set[str]) -> None:
    if not root.exists():
        return
    cutoff = time.time() - JOB_TTL_SECONDS
    for path in root.iterdir():
        if path.is_dir() and path.name not in active_ids and path.stat().st_mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
