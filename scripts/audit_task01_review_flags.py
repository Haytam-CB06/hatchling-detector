"""Expand Task 1 flags into inspectable source-label and duplicate-box records.

Run after audit_task01_model_dataset.py. Writes only under the Task 1 audit dir.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from audit_task01_model_dataset import DEFAULT_OUTPUT, ROOT, inspect_labels, write_csv, write_json


def corners(box: dict) -> tuple[float, float, float, float]:
    return (box["cx"] - box["w"] / 2, box["cy"] - box["h"] / 2,
            box["cx"] + box["w"] / 2, box["cy"] + box["h"] / 2)


def iou(first: dict, second: dict) -> float:
    ax1, ay1, ax2, ay2 = corners(first)
    bx1, by1, bx2, by2 = corners(second)
    overlap = max(0, min(ax2, bx2) - max(ax1, bx1)) * max(0, min(ay2, by2) - max(ay1, by1))
    union = first["w"] * first["h"] + second["w"] * second["h"] - overlap
    return overlap / union if union > 0 else 0.0


def source_issues() -> list[dict]:
    source = ROOT / "data/source/hatchlings_v24"
    rows = []
    for split in ("train", "valid", "test"):
        for label in sorted((source / split / "labels").glob("*.txt")):
            _, issues = inspect_labels(label, {0, 1})
            for issue in issues:
                overshoot = ""
                if issue["issue"] == "invalid_box_coordinate":
                    parts = issue["detail"].split()
                    if len(parts) == 5:
                        cx, cy, width, height = map(float, parts[1:])
                        overshoot = max(0, width / 2 - cx, height / 2 - cy,
                                        cx + width / 2 - 1, cy + height / 2 - 1)
                rows.append({"source_split": split, "label": label.name,
                             "issue": issue["issue"], "line": issue["line"],
                             "detail": issue["detail"], "max_edge_overshoot": overshoot})
    return rows


def duplicate_geometry() -> list[dict]:
    labels = ROOT / "data/generated/hatchling_yolo_v1/labels"
    with (DEFAULT_OUTPUT / "exact_duplicates.csv").open(newline="", encoding="utf-8") as stream:
        duplicates = list(csv.DictReader(stream))
    results = []
    for row in duplicates:
        first = labels / row["split_a"] / (Path(row["filename_a"]).stem + ".txt")
        second = labels / row["split_b"] / (Path(row["filename_b"]).stem + ".txt")
        boxes_a, _ = inspect_labels(first, {0})
        boxes_b, _ = inspect_labels(second, {0})
        best_a = [max((iou(a, b) for b in boxes_b if a["class_id"] == b["class_id"]), default=0)
                  for a in boxes_a]
        best_b = [max((iou(b, a) for a in boxes_a if a["class_id"] == b["class_id"]), default=0)
                  for b in boxes_b]
        values = best_a + best_b
        results.append({"split": row["split_a"], "group": row["group_a"],
                        "filename_a": row["filename_a"], "filename_b": row["filename_b"],
                        "boxes_a": len(boxes_a), "boxes_b": len(boxes_b),
                        "same_label_signature": row["same_label_signature"],
                        "minimum_best_match_iou": round(min(values), 4) if values else "",
                        "mean_best_match_iou": round(sum(values) / len(values), 4) if values else ""})
    return results


def duplicate_contact_sheet(rows: list[dict]) -> None:
    flagged = [row for row in rows if row["same_label_signature"] == "False"]
    if not flagged:
        return
    tile_w, tile_h = 360, 245
    sheet = Image.new("RGB", (2 * tile_w, len(flagged) * tile_h), "#f1f1f1")
    draw = ImageDraw.Draw(sheet)
    for index, row in enumerate(flagged):
        for column, side in enumerate(("a", "b")):
            split = row["split"]
            filename = row[f"filename_{side}"]
            image_path = ROOT / "data/generated/hatchling_yolo_v1/images" / split / filename
            label_path = ROOT / "data/generated/hatchling_yolo_v1/labels" / split / (Path(filename).stem + ".txt")
            boxes, _ = inspect_labels(label_path, {0})
            with Image.open(image_path) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                image.thumbnail((tile_w - 20, tile_h - 48))
            overlay = ImageDraw.Draw(image)
            for box in boxes:
                x1, y1, x2, y2 = corners(box)
                overlay.rectangle((x1 * image.width, y1 * image.height,
                                   x2 * image.width, y2 * image.height),
                                  outline="#ff3131" if column == 0 else "#0066ff", width=2)
            x = column * tile_w + (tile_w - image.width) // 2
            y = index * tile_h + 25 + (tile_h - 48 - image.height) // 2
            sheet.paste(image, (x, y))
            draw.text((column * tile_w + 5, index * tile_h + 5),
                      f"{row['group']} / {'A' if column == 0 else 'B'}", fill="#111111")
            if column == 1:
                draw.text((column * tile_w + 5, index * tile_h + tile_h - 17),
                          f"min best IoU={row['minimum_best_match_iou']}", fill="#111111")
    sheet.save(DEFAULT_OUTPUT / "duplicate_box_disagreements.jpg", quality=92)


def main() -> None:
    DEFAULT_OUTPUT.mkdir(parents=True, exist_ok=True)
    issues = source_issues()
    duplicates = duplicate_geometry()
    duplicate_contact_sheet(duplicates)
    write_csv(DEFAULT_OUTPUT / "source_label_issues.csv", issues,
              ["source_split", "label", "issue", "line", "detail", "max_edge_overshoot"])
    write_csv(DEFAULT_OUTPUT / "duplicate_label_geometry.csv", duplicates,
              ["split", "group", "filename_a", "filename_b", "boxes_a", "boxes_b",
               "same_label_signature", "minimum_best_match_iou", "mean_best_match_iou"])
    overshoots = [float(row["max_edge_overshoot"]) for row in issues if row["max_edge_overshoot"] != ""]
    summary = {"source_issue_counts": dict(Counter(row["issue"] for row in issues)),
               "source_max_edge_overshoot": max(overshoots) if overshoots else None,
               "exact_duplicate_pairs": len(duplicates),
               "duplicate_geometry_disagreements": sum(row["same_label_signature"] == "False" for row in duplicates),
               "minimum_duplicate_box_best_match_iou": min((row["minimum_best_match_iou"] for row in duplicates
                                                              if row["minimum_best_match_iou"] != ""), default=None)}
    write_json(DEFAULT_OUTPUT / "review_flags_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
