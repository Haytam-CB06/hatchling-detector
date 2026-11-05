"""Carry verified preview annotation edits into a newly imported full dataset.

The source labels in both datasets must match exactly. Only samples whose
reviewed labels differ from source labels are copied, and the target's source
labels are never changed.
"""

from __future__ import annotations

import argparse
import copy
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = PROJECT_ROOT / "data" / "fiftyone_db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FIFTYONE_DATABASE_DIR", str(DATABASE_DIR))

import fiftyone as fo  # noqa: E402


def signature(labels: fo.Detections) -> tuple:
    return tuple((d.label, tuple(d.bounding_box)) for d in labels.detections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    if args.preview == args.target:
        parser.error("Preview and target datasets must differ")

    preview = fo.load_dataset(args.preview)
    target = fo.load_dataset(args.target)
    target_by_path = {sample.filepath: sample for sample in target}
    changed = []
    for sample in preview:
        original = signature(sample["ground_truth_source"])
        reviewed = signature(sample["ground_truth_reviewed"])
        if original == reviewed:
            continue
        match = target_by_path.get(sample.filepath)
        if match is None:
            raise RuntimeError(f"Preview image absent from target: {sample.filepath}")
        if signature(match["ground_truth_source"]) != original:
            raise RuntimeError(f"Original labels differ for {sample.filepath}")
        if signature(match["ground_truth_reviewed"]) != original:
            raise RuntimeError(f"Target already has a review for {sample.filepath}")
        changed.append((sample, match))

    for sample, match in changed:
        match["ground_truth_reviewed"] = copy.deepcopy(sample["ground_truth_reviewed"])
        match.save()
        print("Merged review:", Path(sample.filepath).name)
    print(f"Merged {len(changed)} reviewed samples into {target.name}")


if __name__ == "__main__":
    main()
