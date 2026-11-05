"""Import a small, persistent review sample from the original YOLO dataset.

Example (after `conda activate nazar-vision`):
    python scripts/import_yolo_sample.py \
        --source data/source/sea_turtles_hatchling_detection_v24 \
        --name nazar_hatchlings_v24_preview --max-per-split 10

The source directory is only read. FiftyOne stores references to its images and
labels in the project's separate MongoDB database.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = PROJECT_ROOT / "data" / "fiftyone_db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FIFTYONE_DATABASE_DIR", str(DATABASE_DIR))

import fiftyone as fo  # noqa: E402


def resolve_images_dir(source: Path, raw_path: str) -> Path:
    """Resolve common YOLO exports without changing their original data.yaml."""
    path = Path(raw_path)
    candidates = [path] if path.is_absolute() else [source / path]
    if not path.is_absolute():
        # Roboflow writes ../train/images even when data.yaml is at the export
        # root. In that layout the leading '..' must be ignored.
        parts = list(path.parts)
        while parts and parts[0] in ("..", "."):
            parts.pop(0)
        if parts:
            candidates.append(source.joinpath(*parts))
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir():
            return resolved
    raise ValueError(f"Image directory {raw_path!r} does not exist under {source}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Extracted YOLO dataset root containing data.yaml")
    parser.add_argument("--name", default="nazar_hatchlings_v24_preview")
    parser.add_argument("--max-per-split", type=int, default=10)
    parser.add_argument("--all", action="store_true", help="Import every image in each available split")
    args = parser.parse_args()

    source = args.source.resolve(strict=True)
    yaml_path = source / "data.yaml"
    if not yaml_path.is_file():
        parser.error(f"Missing {yaml_path}. Extract the YOLO export first.")
    if not args.all and args.max_per_split < 1:
        parser.error("--max-per-split must be at least 1")
    if fo.dataset_exists(args.name):
        parser.error(f"FiftyOne dataset {args.name!r} already exists. Choose a new name to preserve the existing review.")

    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        parser.error("data.yaml must contain a mapping")
    source_classes = config.get("names")
    if isinstance(source_classes, dict):
        source_classes = [source_classes[k] for k in sorted(source_classes, key=lambda x: int(x))]
    if not isinstance(source_classes, list) or set(source_classes) != {"sea turtle", "non-sea-turtle"}:
        parser.error(f"Unexpected source classes: {source_classes!r}. Inspect this dataset before import.")
    splits = [split for split in ("train", "val", "test") if config.get(split)]
    if not splits:
        parser.error("data.yaml has no train, val, or test image paths")

    normalized = {"nc": len(source_classes), "names": source_classes}
    for split in splits:
        raw_paths = config[split]
        if isinstance(raw_paths, str):
            raw_paths = [raw_paths]
        if not isinstance(raw_paths, list) or not all(isinstance(p, str) for p in raw_paths):
            parser.error(f"Invalid {split} paths in data.yaml: {raw_paths!r}")
        try:
            directories = [str(resolve_images_dir(source, p)) for p in raw_paths]
        except ValueError as exc:
            parser.error(str(exc))
        normalized[split] = directories[0] if len(directories) == 1 else directories

    dataset = fo.Dataset(args.name)
    try:
        with tempfile.TemporaryDirectory(prefix="nazar_yolo_import_") as temp_dir:
            import_yaml = Path(temp_dir) / "data.yaml"
            import_yaml.write_text(yaml.safe_dump(normalized), encoding="utf-8")
            for split in splits:
                before = len(dataset)
                dataset.add_dir(
                    dataset_dir=str(source),
                    dataset_type=fo.types.YOLOv5Dataset,
                    yaml_path=str(import_yaml),
                    split=split,
                    tags=split,
                    label_field="ground_truth_source",
                    max_samples=None if args.all else args.max_per_split,
                )
                print(f"{split}: imported {len(dataset) - before} samples")
        if not len(dataset):
            raise RuntimeError("No images were imported; inspect paths in data.yaml")
        dataset.clone_sample_field("ground_truth_source", "ground_truth_reviewed")
        dataset.info["source_yaml"] = str(yaml_path)
        dataset.info["source_classes"] = source_classes
        dataset.info["import_limit_per_split"] = None if args.all else args.max_per_split
        dataset.persistent = True
        dataset.save()
    except Exception:
        # Leave any partial import for inspection rather than silently deleting it.
        raise

    print(f"Persistent dataset: {dataset.name} ({len(dataset)} samples)")
    print("Source files remain in:", source)
    print("Review only ground_truth_reviewed. Keep ground_truth_source as the original reference.")
    print("Next: python scripts/open_fiftyone.py --dataset", dataset.name)


if __name__ == "__main__":
    main()
