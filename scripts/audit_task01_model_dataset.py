"""Read-only, reproducible audit of the Nazar Vision YOLO export and run.

Run from the project root in the existing Conda environment:
    python scripts/audit_task01_model_dataset.py

Only files in --output are written. Originals, FiftyOne, and weights are read-only.
Perceptual matches are *candidates*, never automatically asserted duplicates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import statistics
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data/generated/hatchling_yolo_v1"
DEFAULT_RUN = ROOT / "artifacts/training/hatchling_n_640"
DEFAULT_EXTERNAL = ROOT / "data/external_test/manifests/combined_manifest.csv"
DEFAULT_CURATION = ROOT / "artifacts/dataset_audit/v24_split_curation.csv"
DEFAULT_OUTPUT = ROOT / "artifacts/model_improvement/task01_audit"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SPLITS = ("train", "val", "test")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def group_key(filename: str) -> str:
    match = re.match(r"(vid\d+)_mp4", filename, re.IGNORECASE)
    if match:
        return "video:" + match.group(1).lower()
    return "image:" + filename.split(".rf.", 1)[0].lower()


def dhash(gray: Image.Image) -> int:
    pixels = np.asarray(gray.resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
    bits = pixels[:, 1:] > pixels[:, :-1]
    return int("".join("1" if bit else "0" for bit in bits.flat), 2)


def phash(gray: Image.Image) -> int:
    pixels = np.asarray(gray.resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32)
    low = cv2.dct(pixels)[:8, :8]
    median = float(np.median(low.flat[1:]))
    return int("".join("1" if value > median else "0" for value in low.flat), 2)


def crop_hashes(gray: Image.Image) -> list[int]:
    width, height = gray.size
    crops = [(0.1, 0.1, 0.9, 0.9), (0, 0, 0.8, 0.8), (0.2, 0, 1, 0.8),
             (0, 0.2, 0.8, 1), (0.2, 0.2, 1, 1)]
    return [phash(gray.crop((round(x1 * width), round(y1 * height),
                             round(x2 * width), round(y2 * height))))
            for x1, y1, x2, y2 in crops]


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def quantiles(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    array = np.asarray(values, dtype=float)
    return {"min": round(float(array.min()), 4),
            "p10": round(float(np.percentile(array, 10)), 4),
            "median": round(float(np.median(array)), 4),
            "p90": round(float(np.percentile(array, 90)), 4),
            "max": round(float(array.max()), 4)}


def read_image(path: Path) -> dict:
    # verify() checks file structure; load() checks the complete pixel stream.
    with Image.open(path) as raw:
        raw.verify()
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")
        image.load()
    gray = image.convert("L")
    pixels = np.asarray(image)
    return {"width": image.width, "height": image.height,
            "pixel_sha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
            "dhash": dhash(gray), "phash": phash(gray),
            "crop_phashes": crop_hashes(gray)}


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n",
                    encoding="utf-8")


def inspect_labels(path: Path, valid_classes: set[int]) -> tuple[list[dict], list[dict]]:
    boxes, issues = [], []
    if not path.exists():
        return boxes, [{"issue": "missing_label_file", "line": "", "detail": "YOLO permits unlabeled negatives; review intent"}]
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (UnicodeError, OSError) as exc:
        return boxes, [{"issue": "unreadable_label_file", "line": "", "detail": str(exc)}]
    for line_no, text in enumerate(lines, 1):
        text = text.strip()
        if not text:
            continue
        parts = text.split()
        if len(parts) != 5:
            issues.append({"issue": "wrong_column_count", "line": line_no, "detail": text})
            continue
        try:
            cls_value = float(parts[0])
            values = [float(item) for item in parts[1:]]
        except ValueError:
            issues.append({"issue": "non_numeric_label", "line": line_no, "detail": text})
            continue
        if not all(map(math.isfinite, [cls_value, *values])):
            issues.append({"issue": "non_finite_coordinate", "line": line_no, "detail": text})
            continue
        if not cls_value.is_integer() or int(cls_value) not in valid_classes:
            issues.append({"issue": "invalid_class_id", "line": line_no, "detail": text})
            continue
        cx, cy, width, height = values
        if (width <= 0 or height <= 0 or width > 1 or height > 1 or
                cx < 0 or cx > 1 or cy < 0 or cy > 1 or
                cx - width / 2 < -1e-6 or cx + width / 2 > 1 + 1e-6 or
                cy - height / 2 < -1e-6 or cy + height / 2 > 1 + 1e-6):
            issues.append({"issue": "invalid_box_coordinate", "line": line_no, "detail": text})
            continue
        boxes.append({"class_id": int(cls_value), "cx": cx, "cy": cy,
                      "w": width, "h": height, "line": line_no})
    return boxes, issues


def pair_row(first: dict, second: dict) -> dict:
    dh = hamming(first["dhash"], second["dhash"])
    ph = hamming(first["phash"], second["phash"])
    crop = min([hamming(first["phash"], value) for value in second["crop_phashes"]] +
               [hamming(second["phash"], value) for value in first["crop_phashes"]])
    return {"split_a": first["split"], "filename_a": first["filename"],
            "split_b": second["split"], "filename_b": second["filename"],
            "group_a": first["group"], "group_b": second["group"],
            "dhash_distance": dh, "phash_distance": ph,
            "crop_phash_distance": crop,
            "same_file_sha256": first["file_sha256"] == second["file_sha256"],
            "same_decoded_pixels": first["pixel_sha256"] == second["pixel_sha256"],
            "same_group_key": first["group"] == second["group"],
            "same_label_signature": (first.get("label_signature") == second.get("label_signature")
                                     if "label_signature" in first and "label_signature" in second else "")}


def pair_score(row: dict) -> tuple:
    return (min(row["dhash_distance"], row["phash_distance"],
                row["crop_phash_distance"]),
            row["phash_distance"], row["dhash_distance"], row["filename_a"], row["filename_b"])


def contact_sheet(path: Path, pairs: list[dict], lookup: dict[tuple[str, str], Path],
                  max_pairs: int = 24) -> None:
    selected = pairs[:max_pairs]
    if not selected:
        return
    tile_w, tile_h = 320, 230
    sheet = Image.new("RGB", (tile_w * 2, tile_h * len(selected)), "#eeeeee")
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(selected):
        for column, side in enumerate(("a", "b")):
            split, filename = row[f"split_{side}"], row[f"filename_{side}"]
            source = lookup.get((split, filename))
            if source and source.exists():
                try:
                    with Image.open(source) as raw:
                        image = ImageOps.exif_transpose(raw).convert("RGB")
                        image.thumbnail((tile_w - 12, tile_h - 50))
                        x = column * tile_w + (tile_w - image.width) // 2
                        y = index * tile_h + 28 + (tile_h - 50 - image.height) // 2
                        sheet.paste(image, (x, y))
                except (OSError, UnidentifiedImageError):
                    pass
            label = f"{index + 1:02d} {split}: {filename[:37]}"
            draw.text((column * tile_w + 5, index * tile_h + 5), label, fill="#111111")
            if column == 1:
                distances = (f"d={row['dhash_distance']} p={row['phash_distance']} "
                             f"crop={row['crop_phash_distance']}")
                draw.text((column * tile_w + 5, index * tile_h + tile_h - 17),
                          distances, fill="#222222")
    sheet.save(path, quality=90)


def metrics_summary(run_dir: Path) -> dict:
    csv_path = run_dir / "results.csv"
    with csv_path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"Empty results.csv: {csv_path}")
    keys = ("metrics/precision(B)", "metrics/recall(B)", "metrics/mAP50(B)",
            "metrics/mAP50-95(B)", "train/box_loss", "train/cls_loss",
            "train/l1_loss", "val/box_loss", "val/cls_loss", "val/l1_loss")
    for row in rows:
        for key in keys:
            row[key] = float(row[key])
        row["epoch"] = int(row["epoch"])
        row["time"] = float(row["time"])
    best = max(rows, key=lambda row: row["metrics/mAP50-95(B)"])
    last = rows[-1]
    def values(row: dict) -> dict:
        return {"epoch": row["epoch"], "precision": row[keys[0]],
                "recall": row[keys[1]], "map50": row[keys[2]],
                "map50_95": row[keys[3]],
                "train_losses": {key: row[key] for key in keys[4:7]},
                "val_losses": {key: row[key] for key in keys[7:]}}
    first_window = rows[:min(5, len(rows))]
    last_window = rows[-min(5, len(rows)):]
    return {"epoch_rows": len(rows), "best_map50_95_epoch": values(best),
            "last_epoch": values(last), "elapsed_seconds_at_last_row": last["time"],
            "first_five_means": {key: statistics.mean(row[key] for row in first_window) for key in keys},
            "last_five_means": {key: statistics.mean(row[key] for row in last_window) for key in keys},
            "best_map50_epoch": max(rows, key=lambda row: row[keys[2]])["epoch"],
            "max_precision_epoch": max(rows, key=lambda row: row[keys[0]])["epoch"],
            "max_recall_epoch": max(rows, key=lambda row: row[keys[1]])["epoch"]}


def environment_summary() -> dict:
    info = {"python": platform.python_version(), "platform": platform.platform(),
            "processor": platform.processor(), "cpu_logical_count": os.cpu_count(),
            "pillow": Image.__version__, "opencv": cv2.__version__, "numpy": np.__version__,
            "pyyaml": yaml.__version__}
    try:
        import psutil
        info["ram_total_bytes"] = psutil.virtual_memory().total
        info["ram_available_bytes_at_audit"] = psutil.virtual_memory().available
        info["disk_free_bytes_at_audit"] = psutil.disk_usage(str(ROOT)).free
        info["cpu_physical_count"] = psutil.cpu_count(logical=False)
    except ImportError:
        info["resource_inventory_note"] = "psutil not installed"
    try:
        import torch
        import ultralytics
        import fiftyone
        info.update({"torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
                     "cuda_device_count": torch.cuda.device_count(),
                     "ultralytics": ultralytics.__version__, "fiftyone": fiftyone.__version__})
    except (ImportError, OSError) as exc:
        info["ml_import_error"] = str(exc)
    return info


def source_inventory(source_dir: Path, exported_names: set[str]) -> dict:
    source_yaml = yaml.safe_load((source_dir / "data.yaml").read_text(encoding="utf-8"))
    classes = {int(key): str(value) for key, value in source_yaml["names"].items()} if isinstance(source_yaml["names"], dict) else dict(enumerate(source_yaml["names"]))
    summary = {"source_yaml": str(source_dir / "data.yaml"), "classes": classes,
               "splits": {}, "total_images": 0, "total_objects": 0,
               "class_objects": Counter(), "missing_labels": 0,
               "invalid_label_rows": 0, "source_filenames_absent_from_export": []}
    for split in ("train", "valid", "test"):
        images = sorted(path for path in (source_dir / split / "images").iterdir()
                        if path.is_file() and path.suffix.lower() in IMAGE_EXTS)
        label_dir = source_dir / split / "labels"
        counts = Counter()
        for image in images:
            boxes, issues = inspect_labels(label_dir / f"{image.stem}.txt", set(classes))
            counts["objects"] += len(boxes)
            counts["positive_sea_turtle_images"] += int(any(box["class_id"] == 1 for box in boxes))
            counts["negative_or_other_class_images"] += int(not any(box["class_id"] == 1 for box in boxes))
            summary["class_objects"].update(box["class_id"] for box in boxes)
            summary["missing_labels"] += sum(issue["issue"] == "missing_label_file" for issue in issues)
            summary["invalid_label_rows"] += sum(issue["issue"] != "missing_label_file" for issue in issues)
            if image.name not in exported_names:
                summary["source_filenames_absent_from_export"].append(image.name)
        summary["splits"][split] = {"images": len(images), **dict(counts)}
        summary["total_images"] += len(images)
        summary["total_objects"] += counts["objects"]
    summary["class_objects"] = dict(summary["class_objects"])
    return summary


def checkpoint_inspection(path: Path) -> dict:
    from ultralytics import YOLO

    model = YOLO(str(path))
    return {"path": str(path), "sha256": sha256(path), "task": model.task,
            "classes": {int(key): str(value) for key, value in model.names.items()},
            "parameter_count": sum(parameter.numel() for parameter in model.model.parameters()),
            "checkpoint_epoch": model.ckpt.get("epoch") if model.ckpt else None,
            "checkpoint_train_args": model.ckpt.get("train_args") if model.ckpt else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--external-manifest", type=Path, default=DEFAULT_EXTERNAL)
    parser.add_argument("--curation", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    dataset_dir, run_dir, output = args.dataset.resolve(), args.run.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    dataset_yaml = yaml.safe_load((dataset_dir / "dataset.yaml").read_text(encoding="utf-8"))
    names = dataset_yaml["names"]
    classes = {int(key): str(value) for key, value in names.items()} if isinstance(names, dict) else dict(enumerate(names))

    curation = {}
    if args.curation.exists():
        with args.curation.open(newline="", encoding="utf-8-sig") as stream:
            curation = {row["filename"]: row for row in csv.DictReader(stream)}

    samples, label_issues, orphan_labels = [], [], []
    boxes_all, image_issues = [], []
    for split in SPLITS:
        image_dir, label_dir = dataset_dir / "images" / split, dataset_dir / "labels" / split
        images = sorted((path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTS),
                        key=lambda path: path.name.lower())
        labels = sorted(label_dir.glob("*.txt"))
        stems = {path.stem for path in images}
        orphan_labels.extend({"split": split, "label": str(path.relative_to(dataset_dir))}
                             for path in labels if path.stem not in stems)
        for path in images:
            label_path = label_dir / f"{path.stem}.txt"
            parsed, issues = inspect_labels(label_path, set(classes))
            for issue in issues:
                label_issues.append({"split": split, "image": path.name,
                                     "label": str(label_path.relative_to(dataset_dir)), **issue})
            image_data = None
            try:
                image_data = read_image(path)
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                image_issues.append({"split": split, "image": path.name,
                                     "issue": "decode_failed", "detail": str(exc)})
            label_signature = hashlib.sha256(json.dumps(sorted((box["class_id"],
                round(box["cx"], 6), round(box["cy"], 6), round(box["w"], 6),
                round(box["h"], 6)) for box in parsed)).encode()).hexdigest()
            record = {"split": split, "filename": path.name, "path": str(path),
                      "group": group_key(path.name), "label_path": str(label_path),
                      "label_exists": label_path.exists(), "object_count": len(parsed),
                      "label_signature": label_signature,
                      "class_counts": dict(Counter(box["class_id"] for box in parsed)),
                      "file_sha256": sha256(path), "file_size_bytes": path.stat().st_size,
                      "curation_split": curation.get(path.name, {}).get("curated_split", ""),
                      "original_split": curation.get(path.name, {}).get("original_split", ""),
                      "curation_group": curation.get(path.name, {}).get("group", "")}
            if image_data:
                record.update(image_data)
            samples.append(record)
            for box in parsed:
                boxes_all.append({"split": split, "filename": path.name, **box,
                                  "area_fraction": box["w"] * box["h"],
                                  "width_px": box["w"] * image_data["width"] if image_data else None,
                                  "height_px": box["h"] * image_data["height"] if image_data else None,
                                  "area_px": box["w"] * box["h"] * image_data["width"] * image_data["height"] if image_data else None})

    valid = [sample for sample in samples if "phash" in sample]
    exact_rows, near_rows, group_cross = [], [], []
    nearest_by_sample = {}
    for first, second in combinations(valid, 2):
        same_sha = first["file_sha256"] == second["file_sha256"]
        same_pixels = first["pixel_sha256"] == second["pixel_sha256"]
        same_group = first["group"] == second["group"]
        if first["split"] == second["split"] and not (same_sha or same_pixels):
            continue  # within-split variants are summarized by source group below
        row = pair_row(first, second)
        if same_sha or same_pixels:
            exact_rows.append(row)
        if first["split"] != second["split"]:
            for item in (first, second):
                key = (item["split"], item["filename"])
                if key not in nearest_by_sample or pair_score(row) < pair_score(nearest_by_sample[key]):
                    nearest_by_sample[key] = row
            if same_group:
                group_cross.append(row)
            if not (same_sha or same_pixels) and (row["dhash_distance"] <= 6 or
                                                  row["phash_distance"] <= 8 or
                                                  row["crop_phash_distance"] <= 6):
                near_rows.append(row)
    near_rows.sort(key=pair_score)
    nearest_rows = sorted({(row["split_a"], row["filename_a"], row["split_b"], row["filename_b"]): row
                           for row in nearest_by_sample.values()}.values(), key=pair_score)[:100]

    groups = defaultdict(list)
    for sample in samples:
        groups[sample["group"]].append(sample)
    group_rows = [{"group": key, "count": len(items),
                   "splits": ";".join(sorted({item["split"] for item in items})),
                   "positive_images": sum(item["object_count"] > 0 for item in items),
                   "negative_images": sum(item["object_count"] == 0 for item in items),
                   "filenames": ";".join(item["filename"] for item in items)}
                  for key, items in sorted(groups.items())]

    external_rows = []
    if args.external_manifest.exists():
        with args.external_manifest.open(newline="", encoding="utf-8-sig") as stream:
            manifest = list(csv.DictReader(stream))
        for row in manifest:
            if row.get("kind") != "image":
                continue
            path = ROOT / row["local_path"].replace("\\", "/")
            try:
                data = read_image(path)
            except (OSError, UnidentifiedImageError, ValueError):
                continue
            external = {"split": "external", "filename": path.name,
                        "group": row.get("group_id", ""), "path": str(path),
                        "file_sha256": sha256(path), **data}
            for sample in valid:
                candidate = pair_row(external, sample)
                if (candidate["same_file_sha256"] or candidate["same_decoded_pixels"] or
                    candidate["dhash_distance"] <= 6 or candidate["phash_distance"] <= 8 or
                    candidate["crop_phash_distance"] <= 6):
                    candidate["external_role_from_source"] = row.get("role", "")
                    candidate["external_group_id"] = row.get("group_id", "")
                    external_rows.append(candidate)
    external_rows.sort(key=pair_score)

    pair_fields = ["split_a", "filename_a", "split_b", "filename_b", "group_a", "group_b",
                   "dhash_distance", "phash_distance", "crop_phash_distance",
                   "same_file_sha256", "same_decoded_pixels", "same_group_key", "same_label_signature"]
    write_csv(output / "samples.csv", [{key: value for key, value in row.items() if key not in
              {"path", "label_path", "dhash", "phash", "crop_phashes", "class_counts"}}
              for row in samples], ["split", "filename", "group", "width", "height", "label_exists",
              "object_count", "file_sha256", "pixel_sha256", "file_size_bytes",
              "curation_split", "original_split", "curation_group", "label_signature"])
    write_csv(output / "boxes.csv", boxes_all,
              ["split", "filename", "class_id", "line", "cx", "cy", "w", "h",
               "area_fraction", "width_px", "height_px", "area_px"])
    write_csv(output / "label_issues.csv", label_issues, ["split", "image", "label", "issue", "line", "detail"])
    write_csv(output / "image_issues.csv", image_issues, ["split", "image", "issue", "detail"])
    write_csv(output / "orphan_labels.csv", orphan_labels, ["split", "label"])
    write_csv(output / "exact_duplicates.csv", exact_rows, pair_fields)
    write_csv(output / "cross_split_group_pairs.csv", group_cross, pair_fields)
    write_csv(output / "cross_split_near_candidates.csv", near_rows, pair_fields)
    write_csv(output / "cross_split_nearest_pairs.csv", nearest_rows, pair_fields)
    write_csv(output / "external_overlap_candidates.csv", external_rows,
              pair_fields + ["external_role_from_source", "external_group_id"])
    write_csv(output / "source_groups.csv", group_rows,
              ["group", "count", "splits", "positive_images", "negative_images", "filenames"])
    sample_lookup = {(row["split"], row["filename"]): Path(row["path"]) for row in samples}
    external_lookup = dict(sample_lookup)
    for row in external_rows:
        path = next((ROOT / entry["local_path"].replace("\\", "/") for entry in manifest
                     if Path(entry["local_path"].replace("\\", "/")).name == row["filename_a"]), None)
        if path:
            external_lookup[("external", row["filename_a"])] = path
    contact_sheet(output / "cross_split_near_candidates.jpg", near_rows, sample_lookup)
    contact_sheet(output / "cross_split_nearest_pairs.jpg", nearest_rows, sample_lookup)
    contact_sheet(output / "external_overlap_candidates.jpg", external_rows, external_lookup)

    split_counts = {split: {"images": sum(row["split"] == split for row in samples),
                            "positive_images": sum(row["split"] == split and row["object_count"] > 0 for row in samples),
                            "negative_images": sum(row["split"] == split and row["object_count"] == 0 for row in samples),
                            "objects": sum(row["split"] == split for row in boxes_all)}
                    for split in SPLITS}
    resolutions = Counter(f"{row['width']}x{row['height']}" for row in valid)
    file_errors = Counter(row["issue"] for row in label_issues)
    box_areas = [row["area_fraction"] for row in boxes_all]
    box_widths = [row["width_px"] for row in boxes_all if row["width_px"] is not None]
    box_heights = [row["height_px"] for row in boxes_all if row["height_px"] is not None]
    box_pixel_areas = [row["area_px"] for row in boxes_all if row["area_px"] is not None]
    summary = {"dataset_yaml": str(dataset_dir / "dataset.yaml"), "classes": classes,
               "total_images": len(samples), "total_objects": len(boxes_all),
               "splits": split_counts, "class_objects": dict(Counter(row["class_id"] for row in boxes_all)),
               "missing_label_files": file_errors.get("missing_label_file", 0),
               "annotation_issue_counts": dict(file_errors), "orphan_label_files": len(orphan_labels),
               "image_decode_failures": len(image_issues), "resolution_counts": dict(resolutions),
               "width_px": quantiles([row["width"] for row in valid]),
               "height_px": quantiles([row["height"] for row in valid]),
               "box_area_fraction": quantiles(box_areas),
               "box_width_px": quantiles(box_widths), "box_height_px": quantiles(box_heights),
               "box_area_px": quantiles(box_pixel_areas),
               "box_coco_small_under_32x32_px": sum(area < 32 ** 2 for area in box_pixel_areas),
               "box_coco_medium_32x32_to_96x96_px": sum(32 ** 2 <= area < 96 ** 2 for area in box_pixel_areas),
               "box_coco_large_96x96_px_or_more": sum(area >= 96 ** 2 for area in box_pixel_areas),
               "source_groups": len(groups),
               "multi_image_source_groups": sum(len(items) > 1 for items in groups.values()),
               "cross_split_source_groups": sum(len({item["split"] for item in items}) > 1 for items in groups.values()),
               "curation_manifest_rows": len(curation),
               "curation_split_mismatches": sum(row["curation_split"] != row["split"] for row in samples),
               "curation_group_mismatches": sum(row["curation_group"].lower() != row["group"] for row in samples),
               "exact_duplicate_pairs": len(exact_rows),
               "exact_duplicate_label_disagreements": sum(row["same_label_signature"] is False for row in exact_rows),
               "cross_split_exact_duplicate_pairs": sum(row["split_a"] != row["split_b"] for row in exact_rows),
               "cross_split_same_source_group_pairs": len(group_cross),
               "cross_split_near_candidates": len(near_rows),
               "external_overlap_candidates": len(external_rows),
               "external_exact_overlap_pairs": sum(row["same_file_sha256"] or row["same_decoded_pixels"] for row in external_rows)}
    write_json(output / "dataset_summary.json", summary)
    write_json(output / "source_inventory.json",
               source_inventory(ROOT / "data/source/hatchlings_v24",
                                {sample["filename"] for sample in samples}))
    write_json(output / "metrics_summary.json", metrics_summary(run_dir))
    args_yaml = yaml.safe_load((run_dir / "args.yaml").read_text(encoding="utf-8"))
    weights = {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
               for path in sorted((run_dir / "weights").glob("*.pt"))}
    write_json(output / "training_config.json", {"args_yaml": str(run_dir / "args.yaml"),
                                                  "arguments": args_yaml, "weights": weights,
                                                  "pretrained_initialization": {"path": str(ROOT / "yolo26n.pt"),
                                                      "exists": (ROOT / "yolo26n.pt").exists(),
                                                      "sha256": sha256(ROOT / "yolo26n.pt") if (ROOT / "yolo26n.pt").exists() else None},
                                                  "export_status": (dataset_dir / "EXPORT_STATUS.txt").read_text(encoding="utf-8").strip()})
    write_json(output / "checkpoint_inspection.json", checkpoint_inspection(run_dir / "weights/best.pt"))
    write_json(output / "environment.json", environment_summary())
    print(json.dumps({"output": str(output), "dataset": summary,
                      "best_epoch": metrics_summary(run_dir)["best_map50_95_epoch"]}, indent=2))


if __name__ == "__main__":
    main()
