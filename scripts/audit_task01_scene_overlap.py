"""Targeted scene-overlap check for adjacent `st-*` source names.

The filename group key in the existing split curation groups Roboflow variants
but not adjacent original photographs. This read-only script checks nearby
numeric stems across splits with ORB+RANSAC and writes candidates for review.
It does not infer that two images came from one recording solely from matches.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from audit_task01_model_dataset import DEFAULT_OUTPUT, ROOT, write_csv, write_json


def descriptor(path: Path, orb) -> tuple[list, np.ndarray | None]:
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return [], None
    return orb.detectAndCompute(image, None)


def alignment(first: tuple, second: tuple) -> tuple[int, int]:
    keypoints_a, desc_a = first
    keypoints_b, desc_b = second
    if desc_a is None or desc_b is None:
        return 0, 0
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desc_a, desc_b, k=2)
    good = [a for a, b in pairs if a.distance < 0.75 * b.distance]
    if len(good) < 4:
        return len(good), 0
    xy_a = np.float32([keypoints_a[item.queryIdx].pt for item in good]).reshape(-1, 1, 2)
    xy_b = np.float32([keypoints_b[item.trainIdx].pt for item in good]).reshape(-1, 1, 2)
    _, mask = cv2.findHomography(xy_a, xy_b, cv2.RANSAC, 5)
    return len(good), int(mask.sum()) if mask is not None else 0


def contact_sheet(rows: list[dict], paths: dict[tuple[str, str], Path]) -> None:
    selected = rows[:12]
    if not selected:
        return
    width, height = 340, 250
    sheet = Image.new("RGB", (width * 2, height * len(selected)), "#f2f2f2")
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(selected):
        for column, side in enumerate(("a", "b")):
            group, split = row[f"group_{side}"], row[f"split_{side}"]
            with Image.open(paths[(group, split)]) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                image.thumbnail((width - 12, height - 52))
            x = column * width + (width - image.width) // 2
            y = index * height + 24 + (height - 52 - image.height) // 2
            sheet.paste(image, (x, y))
            draw.text((column * width + 5, index * height + 5), f"{split}: {group}", fill="#111111")
            if column == 1:
                draw.text((column * width + 5, index * height + height - 18),
                          f"RANSAC inliers: {row['homography_inliers']}", fill="#111111")
    sheet.save(DEFAULT_OUTPUT / "cross_split_scene_orb.jpg", quality=90)


def main() -> None:
    with (DEFAULT_OUTPUT / "samples.csv").open(newline="", encoding="utf-8") as stream:
        samples = list(csv.DictReader(stream))
    group_members = defaultdict(list)
    for row in samples:
        if re.fullmatch(r"image:st-\d+_(?:jpg|png)", row["group"]):
            group_members[(row["group"], row["split"])].append(row)
    representatives = {key: ROOT / "data/generated/hatchling_yolo_v1/images" / key[1] /
                       sorted(items, key=lambda item: item["filename"])[0]["filename"]
                       for key, items in group_members.items()}
    orb = cv2.ORB_create(nfeatures=4000)
    features = {key: descriptor(path, orb) for key, path in representatives.items()}
    keys = sorted(representatives)
    rows = []
    for i, (group_a, split_a) in enumerate(keys):
        number_a = int(re.search(r"st-(\d+)", group_a).group(1))
        for group_b, split_b in keys[i + 1:]:
            if split_a == split_b:
                continue
            number_b = int(re.search(r"st-(\d+)", group_b).group(1))
            if abs(number_a - number_b) > 6:
                continue
            matches, inliers = alignment(features[(group_a, split_a)], features[(group_b, split_b)])
            rows.append({"group_a": group_a, "split_a": split_a,
                         "filename_a": representatives[(group_a, split_a)].name,
                         "group_b": group_b, "split_b": split_b,
                         "filename_b": representatives[(group_b, split_b)].name,
                         "numeric_distance": abs(number_a - number_b),
                         "ratio_test_matches": matches, "homography_inliers": inliers})
    rows.sort(key=lambda item: (-item["homography_inliers"], -item["ratio_test_matches"],
                               item["group_a"], item["group_b"]))
    write_csv(DEFAULT_OUTPUT / "cross_split_scene_orb.csv", rows,
              ["group_a", "split_a", "filename_a", "group_b", "split_b", "filename_b",
               "numeric_distance", "ratio_test_matches", "homography_inliers"])
    contact_sheet(rows, representatives)
    summary = {"adjacent_name_cross_split_pairs_checked": len(rows),
               "pairs_with_100_or_more_homography_inliers": sum(row["homography_inliers"] >= 100 for row in rows),
               "top_pairs": rows[:10],
               "method_limit": "ORB alignment confirms shared scene structure, not recording identity"}
    write_json(DEFAULT_OUTPUT / "scene_overlap_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
