"""Capture repository resources and preservation checks for the lifecycle implementation."""
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.platform_jobs import hardware
from backend.app.platform_db import digest

output = ROOT / "artifacts/platform/implementation"
output.mkdir(parents=True, exist_ok=True)
files = []
for current, directories, names in os.walk(ROOT):
    directories[:] = [name for name in directories if name not in {".git", "node_modules", "__pycache__", ".codex-build", ".pytest_cache"}]
    for name in names:
        path = Path(current) / name
        files.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size})
db = ROOT / "artifacts/annotation_review/task03/reviews.sqlite3"
with sqlite3.connect(db) as conn:
    records = {table: conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall() for table in ("reviews", "review_events")}
preserved = {key: hashlib.sha256(json.dumps(value, separators=(',', ':'), default=str).encode()).hexdigest() for key,value in records.items()}
report = {"created_at": datetime.now(timezone.utc).isoformat(), "hardware": hardware(), "files": files,
          "models": [{**file, "sha256": digest(ROOT/file['path'])} for file in files if file['path'].endswith('.pt')],
          "annotation_database": str(db), "annotation_row_counts": {key:len(value) for key,value in records.items()},
          "annotation_content_sha256": preserved,
          "task_implementations": {"1":"audit scripts/reports", "2":"external error analysis scripts/reports", "3":"React/FastAPI review editor + SQLite + verified-only export", "4":"no prior preparation service", "5":"no prior training orchestration service", "6":"no prior registry/evaluation orchestration service"}}
(output/'repository_audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps({key:report[key] for key in ('created_at','hardware','annotation_row_counts','annotation_content_sha256','task_implementations')},indent=2))
