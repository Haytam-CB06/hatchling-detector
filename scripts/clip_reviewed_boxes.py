"""Trim reviewed boxes that slightly cross an image edge; leave source labels intact."""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = PROJECT_ROOT / "data" / "fiftyone_db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FIFTYONE_DATABASE_DIR", str(DATABASE_DIR))

import fiftyone as fo  # noqa: E402

ROUNDING_TOLERANCE = 2e-5
MAX_FIXABLE_OVERFLOW = 0.01


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    dataset = fo.load_dataset(args.dataset)
    fixes = []
    for sample in dataset:
        for detection in sample["ground_truth_reviewed"].detections:
            x, y, w, h = detection.bounding_box
            overflow = max(0.0, -x, -y, x + w - 1, y + h - 1)
            if overflow <= ROUNDING_TOLERANCE:
                continue
            if overflow > MAX_FIXABLE_OVERFLOW or w <= 0 or h <= 0:
                raise RuntimeError(f"Box needs manual review: {sample.filepath}, {detection.bounding_box}")
            left, top = max(0.0, x), max(0.0, y)
            right, bottom = min(1.0, x + w), min(1.0, y + h)
            if right <= left or bottom <= top:
                raise RuntimeError(f"Box has no visible area: {sample.filepath}, {detection.bounding_box}")
            after = [left, top, right - left, bottom - top]
            fixes.append((sample, detection, list(detection.bounding_box), after))

    for sample, detection, before, after in fixes:
        detection.bounding_box = after
        sample.save()

    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("sample_id", "filename", "detection_id", "before_xywh", "after_xywh"))
        for sample, detection, before, after in fixes:
            writer.writerow((sample.id, Path(sample.filepath).name, detection.id, before, after))
    print(f"Clipped {len(fixes)} reviewed boxes; source labels unchanged")
    print("Report:", report)


if __name__ == "__main__":
    main()
