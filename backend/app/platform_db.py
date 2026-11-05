"""Versioned platform catalog, sharing the existing annotation database safely."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class PlatformDB:
    def __init__(self, path: Path, root: Path):
        self.path, self.root = path.resolve(), root.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.migrate()
        self.migrate2()

    def migrate2(self):
        with self.connection() as c:
            if c.execute("SELECT 1 FROM platform_migrations WHERE version=2").fetchone():
                return
            c.executescript("""CREATE TABLE IF NOT EXISTS platform_quality_decisions(
                image_id TEXT NOT NULL REFERENCES platform_images(id),code TEXT NOT NULL,
                reviewer TEXT NOT NULL,evidence TEXT NOT NULL,decision TEXT NOT NULL,created_at TEXT NOT NULL,
                PRIMARY KEY(image_id,code));""")
            c.execute("INSERT INTO platform_migrations VALUES(2,?)", (now(),))

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def all(self, sql, args=()):
        with self.connection() as c:
            return [dict(r) for r in c.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.all(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connection() as c:
            c.execute(sql, args)

    def event(self, kind, entity, data):
        self.execute("INSERT INTO platform_events(id,kind,entity_id,data_json,created_at) VALUES(?,?,?,?,?)",
                     (uid(), kind, entity, json.dumps(data), now()))

    def migrate(self):
        with self.connection() as c:
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='platform_migrations'").fetchone()
            if exists and c.execute("SELECT 1 FROM platform_migrations WHERE version=1").fetchone():
                return
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            preserved = {name: [tuple(r) for r in c.execute(f"SELECT * FROM {name} ORDER BY 1")]
                         for name in ("reviews", "review_events") if name in tables}
        if self.path.is_file() and tables:
            backup_dir = self.root / "backups"
            backup_dir.mkdir(exist_ok=True)
            with sqlite3.connect(self.path) as source:
                destination = sqlite3.connect(backup_dir / f"before_platform_v1_{uid()}.sqlite3")
                try:
                    source.backup(destination)
                finally:
                    destination.close()
        with self.connection() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS platform_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_datasets(
              id TEXT PRIMARY KEY,name TEXT NOT NULL,version TEXT NOT NULL,source TEXT NOT NULL,
              pool TEXT NOT NULL CHECK(pool IN ('training','evaluation')),created_at TEXT NOT NULL,
              state TEXT NOT NULL,root_path TEXT NOT NULL,classes_json TEXT NOT NULL,summary_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_images(
              id TEXT PRIMARY KEY,dataset_id TEXT NOT NULL REFERENCES platform_datasets(id),
              filename TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,
              pool TEXT NOT NULL,source_split TEXT NOT NULL,source_group TEXT NOT NULL,
              original_json TEXT NOT NULL,predictions_json TEXT NOT NULL,issues_json TEXT NOT NULL,
              phash TEXT NOT NULL,dhash TEXT NOT NULL,metadata_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS platform_image_dataset ON platform_images(dataset_id);
            CREATE INDEX IF NOT EXISTS platform_image_hash ON platform_images(sha256);
            CREATE TABLE IF NOT EXISTS platform_suggestions(
              id TEXT PRIMARY KEY,image_id TEXT NOT NULL REFERENCES platform_images(id),model_id TEXT NOT NULL,
              job_id TEXT NOT NULL,boxes_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_groups(
              image_id TEXT PRIMARY KEY REFERENCES platform_images(id),group_id TEXT NOT NULL,split TEXT NOT NULL,
              confirmed INTEGER NOT NULL,reviewer TEXT NOT NULL,evidence TEXT NOT NULL,independent INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_versions(
              id TEXT PRIMARY KEY,name TEXT NOT NULL,created_at TEXT NOT NULL,state TEXT NOT NULL,
              path TEXT NOT NULL,manifest_json TEXT NOT NULL,summary_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_jobs(
              id TEXT PRIMARY KEY,kind TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,
              progress REAL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,payload_json TEXT NOT NULL,
              result_json TEXT NOT NULL,error TEXT,pid INTEGER,cancel_requested INTEGER NOT NULL DEFAULT 0,log_path TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_models(
              id TEXT PRIMARY KEY,name TEXT NOT NULL,architecture TEXT,checkpoint TEXT NOT NULL UNIQUE,
              sha256 TEXT NOT NULL,bytes INTEGER NOT NULL,created_at TEXT NOT NULL,
              dataset_id TEXT,job_id TEXT,pretrained INTEGER NOT NULL,metrics_json TEXT NOT NULL,config_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_evaluations(
              id TEXT PRIMARY KEY,model_id TEXT NOT NULL REFERENCES platform_models(id),
              version_id TEXT NOT NULL REFERENCES platform_versions(id),job_id TEXT NOT NULL,
              created_at TEXT NOT NULL,kind TEXT NOT NULL,settings_json TEXT NOT NULL,result_json TEXT NOT NULL,path TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_reports(
              id TEXT PRIMARY KEY,kind TEXT NOT NULL,created_at TEXT NOT NULL,path TEXT NOT NULL,data_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS platform_events(id TEXT PRIMARY KEY,kind TEXT NOT NULL,entity_id TEXT NOT NULL,data_json TEXT NOT NULL,created_at TEXT NOT NULL);
            """)
            for name, rows in preserved.items():
                if [tuple(r) for r in c.execute(f"SELECT * FROM {name} ORDER BY 1")] != rows:
                    raise RuntimeError("Annotation migration integrity check failed")
            c.execute("INSERT INTO platform_migrations VALUES(1,?)", (now(),))
        self.event("schema_migration", "v1", {"preserved_rows": {k: len(v) for k, v in preserved.items()}})
