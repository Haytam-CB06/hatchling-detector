"""Persistent subprocess jobs, local model registry, and resource preflight."""
from __future__ import annotations

import csv
import importlib.metadata
import json
import math
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import psutil
import torch
import yaml

from .config import ROOT
from .platform_db import PlatformDB, digest, now, uid


def hardware():
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage(str(ROOT))
    packages = {}
    for package in ("ultralytics", "torch", "fastapi", "numpy", "opencv-python", "Pillow", "PyYAML", "psutil"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    return {"cpu_count": os.cpu_count(), "cpu_percent": psutil.cpu_percent(), "ram_total": memory.total,
            "ram_available": memory.available, "ram_used_percent": memory.percent, "disk_free": disk.free,
            "cuda_available": torch.cuda.is_available(), "devices": ["cpu"] + [str(i) for i in range(torch.cuda.device_count())],
            "gpus": [{"id": i, "name": torch.cuda.get_device_name(i), "memory": torch.cuda.get_device_properties(i).total_memory}
                     for i in range(torch.cuda.device_count())], "python": sys.version.split()[0], "packages": packages}


def read_metrics(path):
    if not path.is_file():
        return [], {}
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            try:
                parsed = {k.strip():float(v) for k,v in row.items() if k and v and v.strip() and math.isfinite(float(v))}
                if 'epoch' in parsed: rows.append(parsed)
            except (ValueError,TypeError):
                continue  # A currently appended CSV row can be incomplete.
    if not rows:
        return [], {}
    best = max(rows, key=lambda r: r.get("metrics/mAP50-95(B)", -1))
    return rows, {"precision": best.get("metrics/precision(B)"), "recall": best.get("metrics/recall(B)"),
                  "map50": best.get("metrics/mAP50(B)"), "map50_95": best.get("metrics/mAP50-95(B)"),
                  "epoch": best.get("epoch"), "scope": "logged validation; independence not established", "source": path.relative_to(ROOT).as_posix()}


def register_model(db, path, dataset_id=None, job_id=None, pretrained=False):
    path = path.resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError("Checkpoint must exist inside the project")
    relative = path.relative_to(ROOT).as_posix()
    existing = db.one("SELECT * FROM platform_models WHERE checkpoint=?", (relative,))
    sha = digest(path)
    if existing:
        if sha != existing["sha256"]:
            raise ValueError(f"Registered checkpoint changed: {relative}; register a preserved version instead")
        return existing["id"]
    run = path.parent.parent
    args_path = run / "args.yaml"
    args = yaml.safe_load(args_path.read_text(encoding="utf-8")) if args_path.is_file() else {}
    args = args if isinstance(args, dict) else {}
    _, metrics = read_metrics(run / "results.csv")
    if path.stem in {"last", "resume"} and metrics:
        rows, _ = read_metrics(run / "results.csv")
        last = rows[-1]
        metrics = {"precision": last.get("metrics/precision(B)"), "recall": last.get("metrics/recall(B)"),
                   "map50": last.get("metrics/mAP50(B)"), "map50_95": last.get("metrics/mAP50-95(B)"), "epoch": last.get("epoch"),
                   "scope": "last logged validation; independence not established"}
    model_id = uid()
    name = path.stem if pretrained else f"{run.name} / {path.stem}"
    db.execute("INSERT INTO platform_models VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (
        model_id, name, str(args.get("model", path.name)), relative, sha, path.stat().st_size,
        datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), dataset_id, job_id,
        int(pretrained), json.dumps(metrics), json.dumps(args),))
    db.event("model_registered", model_id, {"sha256": sha, "checkpoint": relative})
    return model_id


def scan_models(db):
    paths = []
    for folder in (ROOT / "artifacts/training", ROOT / "runs"):
        if folder.exists():
            paths.extend(folder.rglob("*.pt"))
    if (ROOT / "yolo26n.pt").is_file():
        paths.append(ROOT / "yolo26n.pt")
    for path in paths:
        register_model(db, path, pretrained=path.parent == ROOT)
    baseline = db.one("SELECT id FROM platform_models WHERE checkpoint=?", ("artifacts/training/hatchling_n_640/weights/best.pt",))
    if baseline and not db.one("SELECT key FROM platform_settings WHERE key='active_model'"):
        db.execute("INSERT INTO platform_settings VALUES('active_model',?)", (baseline["id"],))
    return {"registered_models": len(paths)}


def public_model(row):
    if row:
        row = dict(row)
        row["metrics"] = json.loads(row.pop("metrics_json"))
        row["configuration"] = json.loads(row.pop("config_json"))
    return row


class Jobs:
    def __init__(self, db: PlatformDB):
        self.db = db
        self.lock = threading.Lock()

    def create(self, kind, payload):
        with self.lock:
            if kind in {"train", "evaluate", "suggest"} and self.db.one("SELECT id FROM platform_jobs WHERE kind IN ('train','evaluate','suggest') AND status IN ('queued','running')"):
                raise ValueError("Another model job is using the local compute worker")
            if self.db.one("SELECT COUNT(*) n FROM platform_jobs WHERE status IN ('queued','running')")['n']>=3:
                raise ValueError('Three background jobs are already active; wait before starting more work')
            job_id = uid()
            folder = self.db.root / "jobs" / job_id
            folder.mkdir(parents=True, exist_ok=False)
            logfile = folder / "worker.log"
            self.db.execute("INSERT INTO platform_jobs(id,kind,status,stage,progress,created_at,updated_at,payload_json,result_json,error,pid,log_path) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (job_id, kind, "queued", "queued", None, now(), now(), json.dumps(payload), "{}", None, None, str(logfile)))
            command = [sys.executable, "-s", "-m", "backend.app.platform_worker", "--db", str(self.db.path), "--root", str(self.db.root), "--job", job_id]
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env['PYTHONNOUSERSITE'] = '1'
            env["OMP_NUM_THREADS"] = "2"
            with logfile.open("ab") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                           env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.db.execute("UPDATE platform_jobs SET pid=? WHERE id=?", (process.pid, job_id))
            return self.get(job_id)

    def get(self, job_id):
        row = self.db.one("SELECT * FROM platform_jobs WHERE id=?", (job_id,))
        if not row:
            return None
        alive = True
        if row["status"] in {"queued", "running"} and row["pid"]:
            try:
                command = " ".join(psutil.Process(row["pid"]).cmdline())
                alive = "platform_worker" in command and job_id in command
            except psutil.NoSuchProcess:
                alive = False
            except psutil.AccessDenied:
                alive = True
        if not alive:
            self.db.execute("UPDATE platform_jobs SET status='interrupted',stage='interrupted',error=?,updated_at=? WHERE id=?", ("Worker exited before recording completion; logs and checkpoints are preserved", now(), job_id))
            row["status"] = "interrupted"
            row['stage']='interrupted';row['error']='Worker exited before recording completion; logs and checkpoints are preserved'
        row["payload"] = json.loads(row.pop("payload_json")); row["result"] = json.loads(row.pop("result_json"))
        row['resumable'] = row['kind']=='train' and row['status'] in {'stopped','interrupted','failed'} and ((self.db.root/'experiments'/job_id/'weights/resume.pt').is_file() or (row['status']=='interrupted' and (self.db.root/'experiments'/job_id/'weights/last.pt').is_file()))
        row['elapsed_seconds'] = max(0,(datetime.now(timezone.utc)-datetime.fromisoformat(row['created_at'])).total_seconds()) if row['status'] in {'running','queued'} else max(0,(datetime.fromisoformat(row['updated_at'])-datetime.fromisoformat(row['created_at'])).total_seconds())
        try: row['process_memory_bytes'] = psutil.Process(row['pid']).memory_info().rss if row['pid'] and row['status']=='running' else None
        except (psutil.NoSuchProcess,psutil.AccessDenied): row['process_memory_bytes']=None
        row.pop("log_path", None)
        return row

    def update(self, job_id, **values):
        allowed = {"status", "stage", "progress", "result_json", "error", "cancel_requested"}
        if not values.keys() <= allowed:
            raise ValueError("Invalid job update")
        columns = list(values)
        self.db.execute("UPDATE platform_jobs SET " + ",".join(f"{k}=?" for k in columns) + ",updated_at=? WHERE id=?",
                        tuple(values[k] for k in columns) + (now(), job_id))


def train_preflight(db, payload):
    errors, warnings = [], []
    version = db.one("SELECT * FROM platform_versions WHERE id=?", (payload.get("version_id"),))
    model = db.one("SELECT * FROM platform_models WHERE id=?", (payload.get("model_id"),))
    resources = hardware()
    if not version or version["state"] != "ready":
        errors.append("Select a prepared, ready dataset version")
    else:
        for row in json.loads(version["manifest_json"]):
            for key, checksum in (("image", "source_sha256"), ("label", "label_sha256")):
                file = Path(version["path"]) / row[key]
                if not file.is_file() or digest(file) != row[checksum]:
                    errors.append(f"Prepared {key} failed checksum verification: {row['image_id']}")
        if not json.loads(version["summary_json"])["ready"]:
            errors.append("Dataset readiness gate failed")
    if not model or digest(ROOT / model["checkpoint"]) != model["sha256"]:
        errors.append("Select an intact registered checkpoint")
    device = payload.get("device", "cpu")
    if device not in resources["devices"]:
        errors.append("Requested device is unavailable")
    limits = {"epochs": (1, 1000), "batch": (1, 64), "imgsz": (128, 2048), "patience": (1, 500), "seed": (0, 2**31-1), "lr0": (1e-6, .1), "mosaic": (0, 1), "max_hours": (.01, 24)}
    for key, (minimum, maximum) in limits.items():
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
            errors.append(f"{key} must be between {minimum} and {maximum}")
    if isinstance(payload.get("imgsz"), int) and payload["imgsz"] % 32:
        errors.append("Image size must be a multiple of 32")
    if payload.get("optimizer") not in {"AdamW", "SGD", "auto"}:
        errors.append("Unsupported optimizer")
    required_disk = max(256_000_000, (model["bytes"] * 8 if model else 0))
    if resources["ram_available"] < 1_500_000_000 or resources["disk_free"] < required_disk:
        errors.append(f"At least 1.5 GB available RAM and {required_disk//1_000_000} MB free working storage are required")
    if device == "cpu":
        warnings.append("CPU training can be slow. The chosen time cap is enforced; elapsed time is not an accuracy estimate.")
        if payload.get("batch", 0) > 8 or payload.get("imgsz", 0) > 1280:
            errors.append("Local CPU jobs are limited to batch 8 and image size 1280")
    if not payload.get("confirm_resources"):
        errors.append("Explicit resource confirmation is required before starting training")
    return {"ready": not errors, "errors": errors, "warnings": warnings, "hardware": resources,
            "duration_estimate": None, "duration_note": "No calibrated runtime estimate is available for this configuration.",
            "dataset": version["name"] if version else None, "model": model["name"] if model else None}
