"""Prove a FiftyOne-format checkpoint restores its samples and media paths."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import uuid

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = PROJECT_ROOT / "data" / "fiftyone_db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FIFTYONE_DATABASE_DIR", str(DATABASE_DIR))

import fiftyone as fo  # noqa: E402


def label_signature(sample: fo.Sample, field: str) -> tuple:
    labels = sample[field]
    if labels is None:
        return ()
    return tuple(sorted((d.label, tuple(d.bounding_box)) for d in labels.detections))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, help="Original FiftyOne dataset name")
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve(strict=True)
    if not (checkpoint / "metadata.json").is_file():
        parser.error(f"Missing checkpoint metadata.json in {checkpoint}")
    source = fo.load_dataset(args.dataset)
    temp_name = f"{args.dataset}_restore_check_{uuid.uuid4().hex[:8]}"
    restored = fo.Dataset.from_dir(
        dataset_dir=str(checkpoint),
        dataset_type=fo.types.FiftyOneDataset,
        name=temp_name,
        persistent=False,
    )
    try:
        original = {sample.filepath: sample for sample in source}
        recovered = {sample.filepath: sample for sample in restored}
        if len(original) != len(source) or original.keys() != recovered.keys():
            raise RuntimeError("Restored sample paths/count differ from the live dataset")
        for path, sample in original.items():
            copy = recovered[path]
            if not Path(path).is_file():
                raise RuntimeError(f"Restored image path is missing: {path}")
            if set(sample.tags) != set(copy.tags):
                raise RuntimeError(f"Restored tags differ: {path}")
            for field in ("ground_truth_source", "ground_truth_reviewed"):
                if label_signature(sample, field) != label_signature(copy, field):
                    raise RuntimeError(f"Restored {field} differs: {path}")
        print(f"Restore verified: {len(restored)} samples; tags, source/reviewed boxes, and media paths match")
    finally:
        fo.delete_dataset(temp_name)


if __name__ == "__main__":
    main()
