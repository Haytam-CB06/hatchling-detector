"""Make version 24 splits independent by original image and source video.

The original split is saved in ``original_split`` on every sample. Source
images, source labels, and reviewed labels are not changed. Run once after
making a FiftyOne checkpoint.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import os
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = PROJECT_ROOT / "data" / "fiftyone_db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FIFTYONE_DATABASE_DIR", str(DATABASE_DIR))

import fiftyone as fo  # noqa: E402

SPLITS = {"train", "val", "test"}
VIDEO_ASSIGNMENTS = {
    "video:vid1": "test",
    "video:vid11": "val",
    "video:vid13": "train",
    "video:vid15": "test",
    "video:vid18": "test",
    "video:vid3": "train",
}
EXPECTED_CROSS_SPLIT_IMAGE_GROUPS = {
    "image:st-10_jpg",
    "image:st-13_jpg",
    "image:st-32_png",
    "image:st-33_png",
    "image:st-34_png",
    "image:st-35_png",
}


def group_key(filepath: str) -> str:
    filename = Path(filepath).name
    match = re.match(r"(vid\d+)_mp4", filename, flags=re.IGNORECASE)
    if match:
        return "video:" + match.group(1).lower()
    return "image:" + filename.split(".rf.", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="nazar_hatchlings_v24_full")
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "artifacts" / "dataset_audit" / "v24_split_curation.csv",
    )
    args = parser.parse_args()
    dataset = fo.load_dataset(args.dataset)
    if "original_split" in dataset.get_field_schema():
        parser.error("This dataset already has original_split; refusing to re-curate it")
    if len(dataset) != 694:
        parser.error(f"Expected version 24's 694 samples, found {len(dataset)}")

    samples = list(dataset)
    groups = defaultdict(list)
    for sample in samples:
        old = SPLITS.intersection(sample.tags)
        if len(old) != 1:
            parser.error(f"{sample.id} has ambiguous split tags: {sample.tags}")
        groups[group_key(sample.filepath)].append((sample, next(iter(old))))

    video_groups = {key for key in groups if key.startswith("video:")}
    if video_groups != set(VIDEO_ASSIGNMENTS):
        parser.error(f"Unexpected video groups: {sorted(video_groups ^ set(VIDEO_ASSIGNMENTS))}")
    cross_split_images = {
        key for key, members in groups.items()
        if key.startswith("image:") and len({old for _, old in members}) > 1
    }
    if cross_split_images != EXPECTED_CROSS_SPLIT_IMAGE_GROUPS:
        parser.error(f"Unexpected cross-split image groups: {sorted(cross_split_images ^ EXPECTED_CROSS_SPLIT_IMAGE_GROUPS)}")

    assignments = {}
    for key, members in groups.items():
        if key in VIDEO_ASSIGNMENTS:
            assignments[key] = VIDEO_ASSIGNMENTS[key]
        else:
            old_splits = {old for _, old in members}
            assignments[key] = "train" if "train" in old_splits else next(iter(old_splits))

    rows = []
    for sample, old in (item for members in groups.values() for item in members):
        key = group_key(sample.filepath)
        new = assignments[key]
        sample["original_split"] = old
        sample["curated_group"] = key
        sample.tags = [tag for tag in sample.tags if tag not in SPLITS] + [new]
        sample.save()
        rows.append((key, old, new, Path(sample.filepath).name))

    report = args.report.resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(("group", "original_split", "curated_split", "filename"))
        writer.writerows(sorted(rows))
    print("Curated split counts:", dict(Counter(row[2] for row in rows)))
    print("Samples moved:", sum(row[1] != row[2] for row in rows))
    print("Cross-split source groups after curation: 0")
    print("Report:", report)


if __name__ == "__main__":
    main()
