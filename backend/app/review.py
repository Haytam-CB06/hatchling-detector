"""Human review of external still images; source media and predictions are read only."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sqlite3
import uuid
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .config import ROOT

STATUSES = {"in_review", "verified_positive", "verified_negative", "ambiguous", "needs_correction", "rejected", "excluded"}
CLASSES = {"hatchling", "adult_turtle", "crab", "bird", "other"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _yolo_axis(lower: float, upper: float, extent: int) -> tuple[str, str]:
    """Derive center and size from the same rounded edges to preserve bounds."""
    precision = Decimal("0.000000000001")
    start = (Decimal(str(lower)) / Decimal(extent)).quantize(precision)
    end = (Decimal(str(upper)) / Decimal(extent)).quantize(precision)
    return format((start + end) / 2, "f"), format(end - start, "f")


class Box(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    class_name: str
    xyxy: tuple[float, float, float, float]
    prediction_id: str | None = None


class ReviewInput(BaseModel):
    status: str
    boxes: list[Box]
    reviewer: str = Field(default="", max_length=100)
    notes: str = Field(default="", max_length=2000)
    revision: int = Field(ge=0)


class ReviewStore:
    def __init__(self, manifest: Path, predictions: Path, db: Path, exports: Path,
                 training_manifest: Path | None = None, training_predictions: Path | None = None):
        self.db = db
        self.exports = exports
        self.items: dict[str, dict] = {}
        self._refreshed_at = 0.0
        sources = [(manifest, predictions, "evaluation")]
        if training_manifest and training_predictions and training_manifest.is_file() and training_predictions.is_file():
            sources.append((training_manifest, training_predictions, "training"))
        for source_manifest, source_predictions, pool in sources:
            with source_predictions.open(encoding="utf-8") as stream:
                prediction_rows = json.load(stream)
            by_media = {str(row["media"]).replace("\\", "/").lower(): row for row in prediction_rows if row.get("kind") == "image"}
            with source_manifest.open(newline="", encoding="utf-8-sig") as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                if row.get("kind") != "image":
                    continue
                relative = row["local_path"].replace("\\", "/")
                path = (ROOT / relative).resolve()
                if not path.is_file() or not path.is_relative_to(ROOT.resolve()):
                    continue
                prediction = by_media.get(relative.lower(), {})
                raw_boxes = prediction.get("predictions", [{}])[0].get("boxes", [])
                boxes = [{"id": f"prediction-{index}", "prediction_id": f"prediction-{index}",
                          "class_name": "hatchling", "confidence": box.get("confidence"),
                          "xyxy": box["xyxy"]} for index, box in enumerate(raw_boxes)]
                identifier = row["sha256"][:16]
                if identifier in self.items:
                    raise ValueError(f"Same image appears in two review pools: {relative}")
                self.items[identifier] = {
                    "id": identifier, "filename": path.name, "path": path,
                    "pool": pool,
                    "source_path": relative, "source_group": row.get("group_id", ""),
                    "source_page": row.get("source_page", ""), "source_title": row.get("title", ""),
                    "source_role": row.get("role", ""), "sha256": row["sha256"],
                    "width": int(row["width"]), "height": int(row["height"]),
                    "predictions": boxes,
                }
        db.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS reviews (
                    image_id TEXT PRIMARY KEY, status TEXT NOT NULL, reviewer TEXT NOT NULL,
                    notes TEXT NOT NULL, boxes_json TEXT NOT NULL, reviewed_at TEXT NOT NULL,
                    revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS review_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT, image_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, saved_at TEXT NOT NULL, reviewer TEXT NOT NULL,
                    status TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
                    changes_json TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def refresh(self):
        if time.monotonic() - self._refreshed_at < .5:
            return
        with self._connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='platform_images'").fetchone():
                return
            rows = conn.execute("SELECT * FROM platform_images").fetchall()
            suggestions = conn.execute("SELECT image_id,boxes_json FROM platform_suggestions ORDER BY created_at").fetchall() if conn.execute("SELECT 1 FROM sqlite_master WHERE name='platform_suggestions'").fetchone() else []
        latest = {r["image_id"]: json.loads(r["boxes_json"]) for r in suggestions}
        self._refreshed_at = time.monotonic()
        for row in rows:
            path = (ROOT / row["path"]).resolve()
            if not path.is_file() or not path.is_relative_to(ROOT.resolve()):
                continue
            previous = self.items.get(row["id"], {})
            metadata = json.loads(row["metadata_json"])
            self.items[row["id"]] = {"id": row["id"], "filename": row["filename"], "path": path,
                "pool": row["pool"], "source_path": row["path"], "source_group": previous.get("source_group") or row["source_group"],
                "source_page": previous.get("source_page") or metadata.get("source_page", ""),
                "source_title": previous.get("source_title") or metadata.get("source_title", row["filename"]),
                "source_role": previous.get("source_role", "unverified import"), "sha256": row["sha256"],
                "width": row["width"], "height": row["height"], "dataset_id": row["dataset_id"],
                "source_split": row["source_split"], "original_annotations": json.loads(row["original_json"]),
                "predictions": json.loads(row["predictions_json"]) or previous.get("predictions", []),
                "issues": json.loads(row["issues_json"])}
            self.items[row["id"]]["suggestions"] = latest.get(row["id"], [])

    def _item(self, image_id: str) -> dict:
        self.refresh()
        item = self.items.get(image_id)
        if item is None:
            raise HTTPException(404, "Image not found")
        return item

    def get(self, image_id: str) -> dict:
        item = self._item(image_id)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reviews WHERE image_id=?", (image_id,)).fetchone()
        public = {key: value for key, value in item.items() if key != "path"}
        public["image_url"] = f"/api/review/images/{image_id}/media"
        public.update({"status": row["status"] if row else "unreviewed",
                       "reviewer": row["reviewer"] if row else "",
                       "notes": row["notes"] if row else "",
                       "reviewed_at": row["reviewed_at"] if row else None,
                       "revision": row["revision"] if row else 0,
                       "boxes": json.loads(row["boxes_json"]) if row else []})
        return public

    def list(self) -> list[dict]:
        self.refresh()
        with self._connect() as conn:
            reviews = {row["image_id"]: dict(row) for row in conn.execute("SELECT * FROM reviews")}
        result = []
        for image_id, item in self.items.items():
            public = {key: value for key, value in item.items() if key not in {"path", "predictions", "original_annotations", "suggestions"}}
            row = reviews.get(image_id, {})
            public.update({"status": row.get("status", "unreviewed"), "reviewer": row.get("reviewer", ""),
                           "notes": row.get("notes", ""), "revision": row.get("revision", 0),
                           "reviewed_at": row.get("reviewed_at"), "image_url": f"/api/review/images/{image_id}/media"})
            result.append(public)
        return result

    def validate(self, item: dict, review: ReviewInput) -> None:
        if review.status not in STATUSES:
            raise HTTPException(422, "Invalid review status")
        ids = set()
        for box in review.boxes:
            if box.id in ids:
                raise HTTPException(422, "Duplicate box ID")
            ids.add(box.id)
            if box.class_name not in CLASSES:
                raise HTTPException(422, "Invalid class name")
            x1, y1, x2, y2 = box.xyxy
            if not all(math.isfinite(value) for value in box.xyxy) or not (0 <= x1 < x2 <= item["width"] and 0 <= y1 < y2 <= item["height"]):
                raise HTTPException(422, "Bounding box must have positive area inside the image")
            if box.prediction_id is not None and box.prediction_id not in {p["id"] for p in item["predictions"]}:
                raise HTTPException(422, "Unknown prediction reference")
        hatchlings = sum(box.class_name == "hatchling" for box in review.boxes)
        if review.status == "verified_positive" and hatchlings == 0:
            raise HTTPException(422, "Verified positive requires a hatchling box")
        if review.status == "verified_negative" and hatchlings:
            raise HTTPException(422, "Verified negative cannot contain hatchling boxes")

    def save(self, image_id: str, review: ReviewInput) -> dict:
        item = self._item(image_id)
        if review.status in {"verified_positive", "verified_negative", "rejected", "excluded"} and not review.reviewer.strip():
            raise HTTPException(422, "Enter a reviewer name for approval, rejection, or exclusion")
        self.validate(item, review)
        new_boxes = [box.model_dump() for box in review.boxes]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute("SELECT * FROM reviews WHERE image_id=?", (image_id,)).fetchone()
            current_revision = previous["revision"] if previous else 0
            if review.revision != current_revision:
                raise HTTPException(409, "Review changed in another session; reopen the image")
            before = json.loads(previous["boxes_json"]) if previous else item["predictions"]
            old_by_id = {box["id"]: box for box in before}
            new_by_id = {box["id"]: box for box in new_boxes}
            changes = {"added": sorted(new_by_id.keys() - old_by_id.keys()),
                       "removed": sorted(old_by_id.keys() - new_by_id.keys()),
                       "modified": sorted(key for key in old_by_id.keys() & new_by_id.keys()
                                          if {k: v for k, v in old_by_id[key].items() if k != "confidence"} != new_by_id[key])}
            changes["image_sha256"] = item["sha256"]
            timestamp = utc_now()
            serialized = json.dumps(new_boxes, separators=(",", ":"))
            conn.execute("""INSERT INTO reviews VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(image_id) DO UPDATE SET status=excluded.status, reviewer=excluded.reviewer,
                notes=excluded.notes, boxes_json=excluded.boxes_json,
                reviewed_at=excluded.reviewed_at, revision=excluded.revision""",
                (image_id, review.status, review.reviewer.strip(), review.notes.strip(), serialized, timestamp, current_revision + 1))
            conn.execute("INSERT INTO review_events(image_id,revision,saved_at,reviewer,status,before_json,after_json,changes_json) VALUES (?,?,?,?,?,?,?,?)",
                         (image_id, current_revision + 1, timestamp, review.reviewer.strip(), review.status,
                          json.dumps(before), serialized, json.dumps(changes)))
        return self.get(image_id)

    def history(self, image_id: str) -> list[dict]:
        self._item(image_id)
        with self._connect() as conn:
            rows = conn.execute("SELECT revision,saved_at,reviewer,status,changes_json FROM review_events WHERE image_id=? ORDER BY revision", (image_id,)).fetchall()
        return [{**{key: row[key] for key in ("revision", "saved_at", "reviewer", "status")},
                 "changes": json.loads(row["changes_json"])} for row in rows]

    def export(self, purpose: Literal["training", "evaluation"] = "training") -> dict:
        self.refresh()
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM reviews WHERE status IN ('verified_positive','verified_negative') ORDER BY image_id").fetchall()
        rows = [row for row in rows if self.items.get(row["image_id"], {}).get("pool") == purpose]
        if not rows:
            raise HTTPException(409, f"No verified {purpose} images to export")
        export_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
        destination = self.exports / purpose / export_id
        images_dir, labels_dir = destination / "images", destination / "labels"
        images_dir.mkdir(parents=True, exist_ok=False)
        labels_dir.mkdir()
        manifest = []
        for row in rows:
            item = self._item(row["image_id"])
            if hashlib.sha256(item["path"].read_bytes()).hexdigest() != item["sha256"]:
                shutil.rmtree(destination)
                raise HTTPException(409, f"Source image changed: {item['filename']}")
            boxes = [Box.model_validate(box) for box in json.loads(row["boxes_json"])]
            self.validate(item, ReviewInput(status=row["status"], boxes=boxes, revision=row["revision"]))
            # Keep export paths short for Windows MAX_PATH and map names in manifest.json.
            stem = item["id"]
            shutil.copyfile(item["path"], images_dir / (stem + item["path"].suffix.lower()))
            lines = []
            for box in boxes:
                if box.class_name != "hatchling":
                    continue
                x1, y1, x2, y2 = box.xyxy
                width, height = item["width"], item["height"]
                xc, bw = _yolo_axis(x1, x2, width)
                yc, bh = _yolo_axis(y1, y2, height)
                lines.append(f"0 {xc} {yc} {bw} {bh}")
            (labels_dir / (stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            manifest.append({"image_id": item["id"], "pool": purpose, "source_path": item["source_path"],
                             "source_group": item["source_group"], "source_sha256": item["sha256"],
                             "status": row["status"], "revision": row["revision"],
                             "reviewer": row["reviewer"], "reviewed_at": row["reviewed_at"],
                             "hatchling_boxes": len(lines)})
        split = "train" if purpose == "training" else "test"
        (destination / "dataset.yaml").write_text(
            "# Reviewed pool only. Group by source event before any experiment.\n"
            f"path: '{destination.resolve().as_posix()}'\n{split}: images\nnames:\n  0: hatchling\n",
            encoding="utf-8",
        )
        (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"export_id": export_id, "purpose": purpose, "path": str(destination), "images": len(manifest),
                "hatchling_boxes": sum(row["hatchling_boxes"] for row in manifest)}


def create_review_router(store: ReviewStore) -> APIRouter:
    router = APIRouter(prefix="/api/review", tags=["annotation review"])

    @router.get("/images")
    def list_images():
        return store.list()

    @router.get("/images/{image_id}")
    def get_image(image_id: str):
        return store.get(image_id)

    @router.get("/images/{image_id}/media")
    def get_media(image_id: str):
        return FileResponse(store._item(image_id)["path"])

    @router.put("/images/{image_id}")
    def save_image(image_id: str, review: ReviewInput):
        return store.save(image_id, review)

    @router.get("/images/{image_id}/history")
    def get_history(image_id: str):
        return store.history(image_id)

    @router.post("/exports")
    def export_verified(purpose: Literal["training", "evaluation"] = "training"):
        return store.export(purpose)

    return router
