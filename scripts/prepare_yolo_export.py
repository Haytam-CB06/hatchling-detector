"""Validate, checkpoint, and export one-class YOLO data.

Choose --provisional for a technical smoke run before full manual review or
--review-complete for a final export. Original images, labels, and
ground_truth_source are never written by this script.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = PROJECT_ROOT / "data" / "fiftyone_db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FIFTYONE_DATABASE_DIR", str(DATABASE_DIR))

import fiftyone as fo  # noqa: E402

SPLITS = {"train", "val", "test", "excluded"}
SOURCE_CLASSES = {"sea turtle", "non-sea-turtle"}
# Roboflow's decimal YOLO coordinates can place a box a few millionths past
# an edge after conversion to FiftyOne's corner-based representation.
BOX_ROUNDING_TOLERANCE = 2e-5


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(dataset: fo.Dataset) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    counts = {split: 0 for split in SPLITS}
    seen_paths: set[Path] = set()
    seen_hashes: dict[str, tuple[str, Path]] = {}

    if len(dataset) == 0:
        errors.append("Dataset is empty")
    for sample in dataset:
        path = Path(sample.filepath).resolve()
        assignments = SPLITS.intersection(sample.tags)
        if len(assignments) != 1:
            errors.append(f"{sample.id}: expected exactly one split/excluded tag, got {sorted(assignments)}")
            continue
        split = next(iter(assignments))
        counts[split] += 1
        if path in seen_paths:
            errors.append(f"Repeated image path: {path}")
        seen_paths.add(path)
        if not path.is_file():
            errors.append(f"Missing image: {path}")
            continue
        digest = file_hash(path)
        if digest in seen_hashes and seen_hashes[digest][0] != split:
            prior_split, prior_path = seen_hashes[digest]
            errors.append(f"Identical image in {prior_split} and {split}: {prior_path} / {path}")
        else:
            seen_hashes[digest] = (split, path)

        for field in ("ground_truth_source", "ground_truth_reviewed"):
            labels = sample[field]
            if labels is None:
                errors.append(f"{sample.id}: missing {field}")
                continue
            for detection in labels.detections:
                if detection.label not in SOURCE_CLASSES:
                    errors.append(f"{sample.id}: unexpected {field} class {detection.label!r}")
                x, y, w, h = detection.bounding_box
                if (
                    w <= 0
                    or h <= 0
                    or min(x, y) < -BOX_ROUNDING_TOLERANCE
                    or x + w > 1 + BOX_ROUNDING_TOLERANCE
                    or y + h > 1 + BOX_ROUNDING_TOLERANCE
                ):
                    errors.append(f"{sample.id}: invalid {field} box {detection.bounding_box}")

    if counts["train"] == 0 or counts["val"] == 0:
        errors.append("Both train and val need at least one sample")
    return errors, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--export-dir", type=Path, required=True)
    status = parser.add_mutually_exclusive_group(required=True)
    status.add_argument("--provisional", action="store_true", help="Technical smoke export; manual review is incomplete")
    status.add_argument("--review-complete", action="store_true", help="Confirm the full manual label review is complete")
    args = parser.parse_args()
    export_dir = args.export_dir.resolve()
    if export_dir.exists():
        parser.error(f"Export directory already exists: {export_dir}")
    if not fo.dataset_exists(args.dataset):
        parser.error(f"Unknown FiftyOne dataset: {args.dataset}")
    dataset = fo.load_dataset(args.dataset)
    errors, counts = validate(dataset)
    print("Split counts:", counts)
    if errors:
        for error in errors[:30]:
            print("ERROR:", error)
        raise SystemExit(f"Validation failed with {len(errors)} error(s); no export was made")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = PROJECT_ROOT / "backups" / f"{dataset.name}_{stamp}"
    dataset.export(
        export_dir=str(backup_dir),
        dataset_type=fo.types.FiftyOneDataset,
        export_media=False,
    )
    print("FiftyOne checkpoint:", backup_dir)

    for sample in dataset:
        canonical = []
        for detection in sample["ground_truth_reviewed"].detections:
            if detection.label == "sea turtle":
                mapped = copy.deepcopy(detection)
                mapped.label = "hatchling"
                x, y, w, h = mapped.bounding_box
                left, top = max(0.0, x), max(0.0, y)
                right, bottom = min(1.0, x + w), min(1.0, y + h)
                mapped.bounding_box = [left, top, right - left, bottom - top]
                canonical.append(mapped)
            # non-sea-turtle annotations are removed from the detector labels.
        sample["ground_truth_canonical"] = fo.Detections(detections=canonical)
        sample.save()

    for split in ("train", "val", "test"):
        if counts[split] == 0:
            continue
        dataset.match_tags(split).export(
            export_dir=str(export_dir),
            dataset_type=fo.types.YOLOv5Dataset,
            label_field="ground_truth_canonical",
            split=split,
            classes=["hatchling"],
        )
    marker = export_dir / "EXPORT_STATUS.txt"
    marker.write_text(
        "PROVISIONAL - for pipeline testing only; manual annotation review is incomplete.\n"
        if args.provisional
        else "REVIEW COMPLETE - final reviewed dataset export.\n",
        encoding="utf-8",
    )
    print("YOLO export:", export_dir)
    print("Inspect data.yaml and exported labels before training.")
    if counts["test"] == 0:
        print("WARNING: no held-out test split. Create one before final evaluation.")


if __name__ == "__main__":
    main()
