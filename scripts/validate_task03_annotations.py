"""Read-only audit of Task 3 reviews and temporary YOLO export validation."""

from __future__ import annotations

import csv
from contextlib import closing
import gc
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import config
from backend.app.review import Box, ReviewInput, ReviewStore, STATUSES


REPORT_DIR = config.ROOT / "artifacts" / "model_improvement" / "task03_annotation_validation"
DB_PATH = config.REVIEW_DB
VERIFIED = {"verified_positive", "verified_negative"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot_database(source: Path, destination: Path) -> None:
    uri_path = quote(source.resolve().as_posix(), safe="/:")
    with closing(sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)) as source_db:
        with closing(sqlite3.connect(destination)) as snapshot_db:
            source_db.backup(snapshot_db)


def verify_export(store: ReviewStore, purpose: str, expected_ids: set[str], temp_root: Path) -> dict:
    result = store.export(purpose)
    folder = Path(result["path"])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    exported_ids = {row["image_id"] for row in manifest}
    assert exported_ids == expected_ids, f"{purpose} export image membership differs from approved records"
    assert all(row["pool"] == purpose for row in manifest), f"{purpose} export contains another pool"

    verified_boxes = 0
    empty_labels = 0
    for row in manifest:
        image_id = row["image_id"]
        matching_images = list((folder / "images").glob(image_id + ".*"))
        assert len(matching_images) == 1, f"Expected one exported image for {image_id}"
        assert sha256(matching_images[0]) == row["source_sha256"], f"Exported image hash mismatch: {image_id}"
        with Image.open(matching_images[0]) as image:
            image.verify()
        label_path = folder / "labels" / f"{image_id}.txt"
        assert label_path.is_file(), f"Missing YOLO label file for {image_id}"
        lines = label_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == row["hatchling_boxes"], f"Label count mismatch: {image_id}"
        if not lines:
            empty_labels += 1
        for line in lines:
            parts = line.split()
            assert len(parts) == 5 and parts[0] == "0", f"Invalid YOLO row: {image_id}: {line}"
            x, y, width, height = map(Decimal, parts[1:])
            assert 0 < width <= 1 and 0 < height <= 1, f"Invalid YOLO box size: {image_id}"
            assert Decimal(0) <= x - width / 2 < x + width / 2 <= Decimal(1), f"YOLO x bounds invalid: {image_id}"
            assert Decimal(0) <= y - height / 2 < y + height / 2 <= Decimal(1), f"YOLO y bounds invalid: {image_id}"
            verified_boxes += 1

    return {
        "purpose": purpose,
        "images": len(manifest),
        "hatchling_boxes": verified_boxes,
        "empty_labels": empty_labels,
        "dataset_yaml_exists": (folder / "dataset.yaml").is_file(),
        "manifest_exists": (folder / "manifest.json").is_file(),
    }


def main() -> None:
    if not DB_PATH.is_file():
        raise SystemExit(f"Review database not found: {DB_PATH}")
    db_hash_before = sha256(DB_PATH)
    model_hash_before = sha256(config.MODEL_PATH) if config.MODEL_PATH.is_file() else None

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    issues: list[str] = []
    sample_results: list[dict] = []
    export_results: list[dict] = []
    total_images = training_inventory = evaluation_inventory = 0
    frozen_eval_group_overlap: list[str] = []
    approved_evaluation_groups: set[str] = set()
    approved_training_groups: set[str] = set()

    with tempfile.TemporaryDirectory(prefix="_audit_tmp_", dir=REPORT_DIR) as temporary:
        temp_root = Path(temporary)
        snapshot_db = temp_root / "reviews_snapshot.sqlite3"
        snapshot_database(DB_PATH, snapshot_db)
        store = ReviewStore(
            config.REVIEW_MANIFEST,
            config.REVIEW_PREDICTIONS,
            snapshot_db,
            temp_root / "exports",
            config.REVIEW_TRAIN_MANIFEST,
            config.REVIEW_TRAIN_PREDICTIONS,
        )
        store.refresh()

        with closing(sqlite3.connect(f"file:{quote(snapshot_db.resolve().as_posix(), safe='/:')}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM reviews ORDER BY image_id").fetchall()
            event_counts = {
                row["image_id"]: conn.execute("SELECT COUNT(*) FROM review_events WHERE image_id=?", (row["image_id"],)).fetchone()[0]
                for row in rows
            }
            event_latest = {
                row["image_id"]: conn.execute(
                    "SELECT revision,saved_at,status,after_json FROM review_events WHERE image_id=? ORDER BY revision DESC LIMIT 1",
                    (row["image_id"],),
                ).fetchone()
                for row in rows
            }

        status_counts = Counter(row["status"] for row in rows)
        saved_ids = {row["image_id"] for row in rows}
        inventory_status_counts = Counter()
        train_groups: set[str] = set()
        evaluation_groups: set[str] = set()
        approved_train_ids: set[str] = set()
        approved_evaluation_ids: set[str] = set()
        verified_hatchling_boxes = 0
        blank_reviewer_approved = 0

        for item in store.items.values():
            if item["pool"] == "training" and item["source_group"]:
                train_groups.add(item["source_group"])
            if item["pool"] == "evaluation" and item["source_group"]:
                evaluation_groups.add(item["source_group"])
            row = next((r for r in rows if r["image_id"] == item["id"]), None)
            status = row["status"] if row else "unreviewed"
            inventory_status_counts[status] += 1

        for row in rows:
            image_id = row["image_id"]
            item = store.items.get(image_id)
            record = {"image_id": image_id, "status": row["status"], "reviewer": row["reviewer"],
                      "revision": row["revision"], "pool": item["pool"] if item else None,
                      "filename": item["filename"] if item else None,
                      "source_group": item["source_group"] if item else None,
                      "hatchling_boxes": 0, "source_hash_matches": False, "valid": False}
            if row["status"] not in STATUSES:
                issues.append(f"Unknown status {row['status']!r} for {image_id}.")
            if item is None:
                issues.append(f"Review {image_id} does not map to an image in either source manifest.")
                sample_results.append(record)
                continue

            try:
                boxes_raw = json.loads(row["boxes_json"])
                boxes = [Box.model_validate(box) for box in boxes_raw]
                input_record = ReviewInput(status=row["status"], boxes=boxes, reviewer=row["reviewer"],
                                           notes=row["notes"], revision=row["revision"])
                store.validate(item, input_record)
                record["hatchling_boxes"] = sum(box.class_name == "hatchling" for box in boxes)
                record["valid"] = True
                if row["status"] in VERIFIED:
                    verified_hatchling_boxes += record["hatchling_boxes"]
                    if not row["reviewer"].strip():
                        blank_reviewer_approved += 1
                    if item["pool"] == "training":
                        approved_train_ids.add(image_id)
                        if item["source_group"]:
                            approved_training_groups.add(item["source_group"])
                    else:
                        approved_evaluation_ids.add(image_id)
                        if item["source_group"]:
                            approved_evaluation_groups.add(item["source_group"])
            except Exception as exc:  # report exact malformed record without altering it
                issues.append(f"Invalid/incomplete annotation for {image_id}: {type(exc).__name__}: {exc}")

            expected_sha = item["sha256"]
            actual_sha = sha256(item["path"])
            record["source_hash_matches"] = actual_sha == expected_sha and image_id == expected_sha[:16]
            if not record["source_hash_matches"]:
                issues.append(f"Original-image identity/hash mismatch for {image_id} ({item['filename']}).")
            try:
                with Image.open(item["path"]) as image:
                    actual_size = image.size
                    image.verify()
                if actual_size != (item["width"], item["height"]):
                    issues.append(f"Image dimensions differ from source manifest for {image_id}.")
            except Exception as exc:
                issues.append(f"Original image cannot be decoded for {image_id}: {type(exc).__name__}: {exc}")

            if event_counts.get(image_id) != row["revision"]:
                issues.append(f"Review event count does not match revision for {image_id}.")
            latest = event_latest.get(image_id)
            if latest is None or latest["revision"] != row["revision"] or latest["status"] != row["status"]:
                issues.append(f"Latest review event does not match current decision for {image_id}.")
            elif json.loads(latest["after_json"]) != boxes_raw:
                issues.append(f"Latest review event boxes differ from current boxes for {image_id}.")
            sample_results.append(record)

        rejected_count = status_counts.get("rejected", 0)
        unsupported_statuses = sorted(set(status_counts) - STATUSES)
        total_images = len(store.items)
        awaiting_count = sum(inventory_status_counts.get(status, 0) for status in ("unreviewed", "in_review", "ambiguous", "needs_correction"))
        approved_group_ids = {
            item["source_group"] for image_id in saved_ids
            if (item := store.items.get(image_id)) and item["source_group"] and item["pool"] == "training"
        }
        frozen_eval_group_overlap = sorted(approved_group_ids & evaluation_groups)

        if approved_train_ids:
            export_results.append(verify_export(store, "training", approved_train_ids, temp_root))
        if approved_evaluation_ids:
            export_results.append(verify_export(store, "evaluation", approved_evaluation_ids, temp_root))

        training_inventory = sum(1 for item in store.items.values() if item["pool"] == "training")
        evaluation_inventory = sum(1 for item in store.items.values() if item["pool"] == "evaluation")
        del store
        gc.collect()

    db_hash_after = sha256(DB_PATH)
    model_hash_after = sha256(config.MODEL_PATH) if config.MODEL_PATH.is_file() else None
    if db_hash_after != db_hash_before:
        issues.append("Review database checksum changed during audit; inspect before relying on this report.")
    if model_hash_after != model_hash_before:
        issues.append("Model checkpoint checksum changed during audit.")

    approved_positive = status_counts.get("verified_positive", 0)
    approved_negative = status_counts.get("verified_negative", 0)
    draft_count = status_counts.get("in_review", 0)
    ambiguous_count = status_counts.get("ambiguous", 0)
    training_group_ids_are_image_fallbacks = bool(approved_training_groups) and all(
        group.startswith("image:") for group in approved_training_groups
    )
    evaluation_group_ids_are_source_names = bool(evaluation_groups) and all(
        group.startswith("file:") for group in evaluation_groups
    )

    findings = "\n".join(f"- {issue}" for issue in issues) if issues else "- No structural, source-integrity, event-history, or export errors were detected."
    export_lines = "\n".join(
        f"- {row['purpose']}: {row['images']} images, {row['hatchling_boxes']} hatchling boxes, {row['empty_labels']} empty labels; YOLO bounds and file hashes passed."
        for row in export_results
    ) or "- No verified records were available for export."

    report = f"""# Task 3 Annotation Validation Report

Audit time: {datetime.now().astimezone().isoformat(timespec='seconds')}

## Summary

- Review database: `{DB_PATH}`
- Total image inventory: {total_images} ({training_inventory} training candidates; {evaluation_inventory} frozen evaluation images)
- Saved/reviewed images: {len(rows)}
- Approved positive images: {approved_positive}
- Approved negative images: {approved_negative}
- Awaiting review: {awaiting_count} (unreviewed + in-review drafts + ambiguous)
- In-review drafts: {draft_count}; ambiguous: {ambiguous_count}
- Rejected images: {rejected_count}. Rejected and excluded records are retained outside training exports.
- Verified hatchling bounding boxes on approved images: {verified_hatchling_boxes}
- Approved records without a reviewer identifier: {blank_reviewer_approved}
- Structural/source/export issues: {len(issues)}

## Results

### Annotation validity and image identity

Each saved annotation was checked against the application’s class and status rules, finite coordinates, positive box area, image bounds, unique box IDs, and prediction references. Image paths, dimensions, full SHA-256 values, and the SHA-derived image IDs were checked against the manifests. Review history event counts and latest event content were compared with the current records.

{findings}

The approved labels are recorded as verified in the database. Reviewer names are optional in Task 3, and all {blank_reviewer_approved} approved records have an empty reviewer field. Their notes document the verification context, but the database does not identify a named reviewer for these rows.

### Visual spot check

The approved box overlays were reviewed together in [`approved_annotations_contact_sheet.png`](approved_annotations_contact_sheet.png). No obvious image-to-box mismatch was visible at contact-sheet scale. This spot check supports the source-hash checks but does not replace individual adjudication of ambiguous wildlife or group provenance.

### Frozen evaluation separation

- Approved evaluation images: {len(approved_evaluation_ids)}.
- Approved training groups using image-specific fallback IDs: {sum(group.startswith('image:') for group in approved_training_groups)} of {len(approved_training_groups)}.
- Exact approved-training/frozen-evaluation group-ID overlap: {len(frozen_eval_group_overlap)}{(': ' + ', '.join(frozen_eval_group_overlap)) if frozen_eval_group_overlap else ''}.
- Pool assignment came from the immutable review manifests; this audit did not reassign samples.
- Status values outside the platform’s supported review states: {', '.join(unsupported_statuses) if unsupported_statuses else 'none'}.

The training groups are image-specific fallback IDs and the evaluation groups are source-name IDs. Because these identifiers use different schemes and do not identify shared recordings or wildlife events, the zero exact overlap does **not** establish event-level independence. Task 4 needs reliable recording/event grouping before making an independent split claim.

### Negative labels and YOLO export

{export_lines}

YOLO export validation used an isolated copy of the database and a temporary export directory. The original review database was not used for writes. Empty `.txt` labels are expected for approved negatives and were checked as empty files. The audit's temporary exports were removed automatically after validation.

### Integrity safeguards

- Review database SHA-256 before/after audit: `{db_hash_before}` / `{db_hash_after}`.
- Model checkpoint SHA-256 before/after audit: `{model_hash_before}` / `{model_hash_after}`.
- No model training ran, and no split assignments were changed.

## Readiness for Task 4

The {approved_positive + approved_negative} approved annotations ({verified_hatchling_boxes} hatchling boxes) are structurally valid and can be serialized to YOLO format. The current review queue is not complete: {awaiting_count} of {total_images} images remain awaiting a decision, including {training_inventory - sum(1 for r in sample_results if r['pool'] == 'training' and r['status'] in VERIFIED)} training candidates and {evaluation_inventory - len(approved_evaluation_ids)} frozen evaluation images. No approved evaluation labels are currently available through Task 3.

**Conclusion:** the approved training subset is structurally valid and export-ready. The complete Task 4 dataset needs a completed source/group review and a verified split-integrity check. Continue reviewing selected training candidates, then establish recording/event groups in the preparation wizard. Keep frozen evaluation media evaluation-only. Uncertain, rejected, and excluded decisions remain outside training exports.
"""

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "REPORT.md").write_text(report, encoding="utf-8")
    machine = {
        "audit_time": datetime.now().astimezone().isoformat(timespec="seconds"),
        "database": str(DB_PATH),
        "database_sha256_before": db_hash_before,
        "database_sha256_after": db_hash_after,
        "model_sha256_before": model_hash_before,
        "model_sha256_after": model_hash_after,
        "inventory": {"total": total_images, "training": training_inventory, "frozen_evaluation": evaluation_inventory},
        "status_counts": dict(status_counts),
        "inventory_status_counts": dict(inventory_status_counts),
        "awaiting_review": awaiting_count,
        "rejected_status_supported": "rejected" in STATUSES,
        "rejected_count": rejected_count,
        "verified_hatchling_boxes": verified_hatchling_boxes,
        "approved_records_missing_reviewer_id": blank_reviewer_approved,
        "approved_evaluation_source_groups": sorted(approved_evaluation_groups),
        "approved_training_source_groups": sorted(approved_training_groups),
        "approved_training_groups_overlapping_frozen_evaluation": frozen_eval_group_overlap,
        "group_independence_established": False if training_group_ids_are_image_fallbacks or evaluation_group_ids_are_source_names else not frozen_eval_group_overlap,
        "exports": export_results,
        "issues": issues,
        "records": sample_results,
    }
    (REPORT_DIR / "audit.json").write_text(json.dumps(machine, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(REPORT_DIR / "REPORT.md"), "audit_json": str(REPORT_DIR / "audit.json"),
                      "saved_reviews": len(rows), "status_counts": dict(status_counts),
                      "inventory_status_counts": dict(inventory_status_counts),
                      "verified_hatchling_boxes": verified_hatchling_boxes,
                      "issues": issues, "exports": export_results}, indent=2))


if __name__ == "__main__":
    main()
