"""Read-only analysis of saved external-test predictions and manual review decisions.

Run from anywhere with the project's Conda Python. Original media, predictions,
and model weights are read but never modified. Outputs are versioned in Task 02.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "external_test"
OUT = ROOT / "artifacts" / "model_improvement" / "task02_error_analysis"
MANIFEST = ROOT / "data" / "external_test" / "manifests" / "combined_manifest.csv"
DECISIONS = OUT / "review_decisions.json"
THRESHOLDS = (0.10, 0.25, 0.40)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def norm(path: str) -> str:
    return path.replace("\\", "/")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frame_image(media_path: Path, frame_index: int | None) -> Image.Image:
    if frame_index is None:
        with Image.open(media_path) as img:
            return img.convert("RGB")
    cap = cv2.VideoCapture(str(media_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open {media_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"Cannot decode frame {frame_index} of {media_path}")
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


def get_font(size: int = 18) -> ImageFont.ImageFont:
    for name in ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf"):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def visual_panel(image: Image.Image, boxes: list[dict], caption: str, width: int = 640) -> Image.Image:
    image_area_height = 400
    scale = min(width / image.width, image_area_height / image.height)
    rendered_width = round(image.width * scale)
    rendered_height = round(image.height * scale)
    x_offset = (width - rendered_width) // 2
    y_offset = 78 + (image_area_height - rendered_height) // 2
    scaled = image.resize((rendered_width, rendered_height), Image.Resampling.LANCZOS)
    board = Image.new("RGB", (width, image_area_height + 78), "#eef2f5")
    board.paste(scaled, (x_offset, y_offset))
    draw = ImageDraw.Draw(board)
    font = get_font(16)
    for box in boxes:
        x1, y1, x2, y2 = box["xyxy"]
        rect = (
            round(x1 * scale) + x_offset,
            round(y1 * scale) + y_offset,
            round(x2 * scale) + x_offset,
            round(y2 * scale) + y_offset,
        )
        draw.rectangle(rect, outline="#165dff", width=3)
        label = f"hatchling {box['confidence']:.2f}"
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0] + 8
        tx, ty = rect[0], max(78, rect[1] - 22)
        draw.rectangle((tx, ty, tx + tw, ty + 22), fill="#165dff")
        draw.text((tx + 4, ty + 1), label, fill="white", font=font)
    for line_number, segment in enumerate((caption[:68], caption[68:136])):
        if segment:
            draw.text((8, 2 + line_number * 19), segment, fill="#111827", font=get_font(15))
    draw.text((8, 43), f"{image.width}x{image.height} | {len(boxes)} saved boxes at >=0.10", fill="#344054", font=get_font(15))
    return board


def grid(items: list[tuple[Image.Image, list[dict], str]], target: Path, columns: int = 2) -> None:
    if not items:
        return
    panels = [visual_panel(image, boxes, caption) for image, boxes, caption in items]
    cell_width = 640
    cell_height = 488
    rows = (len(panels) + columns - 1) // columns
    canvas = Image.new("RGB", (cell_width * columns, cell_height * rows), "#d7dfe7")
    for index, panel in enumerate(panels):
        canvas.paste(panel, ((index % columns) * cell_width, (index // columns) * cell_height))
    canvas.save(target, quality=88)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    predictions = json.loads((SOURCE / "predictions.json").read_text(encoding="utf-8"))
    manifest_rows = read_csv(MANIFEST)
    summary_rows = read_csv(SOURCE / "run_summary.csv")
    manifest = {norm(row["local_path"]): row for row in manifest_rows}
    saved_summary = {norm(row["local_path"]): row for row in summary_rows}
    run_metadata = json.loads((SOURCE / "run_metadata.json").read_text(encoding="utf-8"))
    model_path = ROOT / norm(run_metadata["model"])
    model_hash = sha256(model_path)
    if model_hash.lower() != run_metadata["model_sha256"].lower():
        raise AssertionError("Current checkpoint differs from external prediction run metadata")
    if len(predictions) != len(manifest) or len(predictions) != len(saved_summary):
        raise AssertionError("Prediction/manifest/summary row counts differ")
    if len(manifest) != len(manifest_rows) or len(saved_summary) != len(summary_rows):
        raise AssertionError("Duplicate media paths")

    units = []
    by_key = {}
    media_summary = []
    image_dims = {}
    verified_media_hashes = 0
    for media in predictions:
        path = norm(media["media"])
        if path not in manifest or path not in saved_summary:
            raise AssertionError(f"Unmatched media {path}")
        m = manifest[path]
        if media["kind"] != m["kind"] or media["role"] != m["role"]:
            raise AssertionError(f"Kind/role mismatch {path}")
        media_path = ROOT / path
        if not media_path.is_file():
            raise FileNotFoundError(media_path)
        if sha256(media_path).lower() != m["sha256"].lower():
            raise AssertionError(f"External original differs from manifest checksum: {path}")
        verified_media_hashes += 1
        if media["kind"] == "image":
            image = frame_image(media_path, None)
            image_dims[path] = image.size
            if (image.width, image.height) != (int(m["width"]), int(m["height"])):
                raise AssertionError(f"Dimension mismatch {path}")
        else:
            image = frame_image(media_path, media["predictions"][0]["frame_index"])
            image_dims[path] = image.size
        counts = {t: 0 for t in THRESHOLDS}
        total_boxes = {t: 0 for t in THRESHOLDS}
        for frame in media["predictions"]:
            idx = frame["frame_index"]
            key = (path, idx)
            if key in by_key:
                raise AssertionError(f"Repeated unit {key}")
            boxes = frame["boxes"]
            for box in boxes:
                x1, y1, x2, y2 = box["xyxy"]
                if not (0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height):
                    raise AssertionError(f"Invalid saved box {key}: {box}")
                if not 0.10 <= box["confidence"] <= 1.0:
                    raise AssertionError(f"Invalid saved confidence {key}: {box}")
            row = {
                "identifier": Path(path).name if idx is None else f"{Path(path).name}#frame={idx}",
                "local_path": path,
                "kind": media["kind"],
                "source_role": media["role"],
                "source_group": m["group_id"],
                "source_page": m["source_page"],
                "frame_index": "" if idx is None else idx,
                "time_s": "" if frame["time_s"] is None else frame["time_s"],
                "width": image.width,
                "height": image.height,
                "box_count_010": len(boxes),
                "box_count_025": sum(b["confidence"] >= .25 for b in boxes),
                "box_count_040": sum(b["confidence"] >= .40 for b in boxes),
                "max_confidence": max((b["confidence"] for b in boxes), default=""),
                "boxes_json": json.dumps(boxes, separators=(",", ":")),
            }
            units.append(row)
            by_key[key] = (row, boxes)
            for t in THRESHOLDS:
                n = sum(b["confidence"] >= t for b in boxes)
                counts[t] += n > 0
                total_boxes[t] += n
        prior = saved_summary[path]
        for t, field in ((.10, "frames_with_detection_at_0_10"), (.25, "frames_with_detection_at_0_25"), (.40, "frames_with_detection_at_0_40")):
            if counts[t] != int(prior[field]):
                raise AssertionError(f"Saved run summary differs: {path}, {field}")
        if total_boxes[.10] != int(prior["total_boxes_at_0_10"]):
            raise AssertionError(f"Saved total boxes differ: {path}")
        media_summary.append({"path": path, "role": media["role"], "kind": media["kind"], "units": len(media["predictions"]), "counts": counts, "boxes": total_boxes})

    write_csv(OUT / "all_units_inventory.csv", units, list(units[0]))
    (OUT / "input_integrity.json").write_text(json.dumps({
        "verified_original_media_sha256": verified_media_hashes,
        "manifest_media_count": len(manifest),
        "checkpoint_sha256": model_hash,
        "checkpoint_matches_prediction_run": True,
        "inference_rerun": False,
    }, indent=2) + "\n", encoding="utf-8")
    threshold = {}
    for kind in ("image", "video"):
        for role in ("positive", "negative"):
            group = [r for r in media_summary if r["kind"] == kind and r["role"] == role]
            if not group:
                continue
            threshold[f"{kind}_{role}"] = {
                "media_files": len(group),
                "units": sum(r["units"] for r in group),
                "thresholds": {str(t): {"units_with_box": sum(r["counts"][t] for r in group), "boxes": sum(r["boxes"][t] for r in group)} for t in THRESHOLDS},
            }
    (OUT / "threshold_summary.json").write_text(json.dumps(threshold, indent=2) + "\n", encoding="utf-8")

    # Render every sampled video frame for visual triage; no inference is run.
    for media in predictions:
        if media["kind"] != "video":
            continue
        path = norm(media["media"])
        cap = cv2.VideoCapture(str(ROOT / path))
        if not cap.isOpened():
            raise ValueError(f"Cannot open video {path}")
        panels = []
        for frame in media["predictions"]:
            idx = frame["frame_index"]
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, bgr = cap.read()
            if not ok:
                raise ValueError(f"Cannot decode {path} frame {idx}")
            rgb = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            panels.append((rgb, frame["boxes"], f"{Path(path).stem[:29]} | f={idx} t={frame['time_s']:.1f}s"))
        cap.release()
        for start in range(0, len(panels), 8):
            grid(panels[start:start+8], OUT / f"video_{Path(path).stem[:18]}_{start//8+1:02}.jpg")

    if DECISIONS.exists():
        decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
        allowed_status = {"verified_error", "suspected_error", "incorrect_source_label", "unverifiable", "visual_correct"}
        error_rows = []
        category_counts = Counter()
        category_status_counts = defaultdict(Counter)
        status_counts = Counter()
        used = set()
        for case in decisions:
            filename = case["image_identifier"]
            matching = [key for key in by_key if Path(key[0]).name == filename and key[1] == case.get("frame_index")]
            if len(matching) != 1:
                raise AssertionError(f"Case identifier not unique/present: {filename}, {case.get('frame_index')}")
            key = matching[0]
            if key in used:
                raise AssertionError(f"Repeated review case {key}")
            used.add(key)
            row, boxes = by_key[key]
            if case["verification_status"] not in allowed_status:
                raise AssertionError(f"Bad verification status {case}")
            for required in ("categories", "observed_failure", "possible_explanation", "suggested_corrective_action", "visual_evidence"):
                if required not in case:
                    raise AssertionError(f"Missing {required} in {filename}")
            categories = case["categories"]
            for category in categories:
                category_counts[category] += 1
                category_status_counts[category][case["verification_status"]] += 1
            status_counts[case["verification_status"]] += 1
            error_rows.append({
                **{k: row[k] for k in row if k != "boxes_json"},
                "source_title": manifest[key[0]]["title"],
                "ground_truth_availability": "visual review only; no audited box ground truth",
                "verification_status": case["verification_status"],
                "categories": "|".join(categories),
                "prediction_boxes_json": json.dumps(boxes, separators=(",", ":")),
                "observed_failure": case["observed_failure"],
                "possible_explanation": case["possible_explanation"],
                "suggested_corrective_action": case["suggested_corrective_action"],
                "visual_evidence": case["visual_evidence"],
                "priority": case.get("priority", ""),
            })
        write_csv(OUT / "error_inventory.csv", error_rows, list(error_rows[0]))
        category_rows = [{"category": k, "reviewed_case_count": v, **{status: category_status_counts[k][status] for status in sorted(allowed_status)}} for k, v in sorted(category_counts.items())]
        write_csv(OUT / "error_category_summary.csv", category_rows, list(category_rows[0]))
        prioritized = sorted((r for r in error_rows if r["priority"]), key=lambda r: (int(r["priority"]), r["identifier"]))
        write_csv(OUT / "difficult_samples.csv", prioritized, list(error_rows[0]))
        (OUT / "review_summary.json").write_text(json.dumps({"review_cases": len(error_rows), "status_counts": status_counts, "category_counts": category_counts, "category_status_counts": category_status_counts}, indent=2) + "\n", encoding="utf-8")

        sheet_specs = {
            "correct_detections": lambda r: r["verification_status"] == "visual_correct",
            "suspected_false_positives": lambda r: r["verification_status"] in {"verified_error", "suspected_error"} and r["box_count_010"] > 0,
            "suspected_false_negatives": lambda r: "missed_visible_hatchling" in r["categories"] or "small_object_failure" in r["categories"],
            "adult_turtle_confusion": lambda r: "adult_turtle_confusion" in r["categories"],
            "difficult_backgrounds": lambda r: any(k in r["categories"] for k in ("nest_track_confusion", "background_false_positive", "crab_scene_false_positive", "bird_confusion")),
            "small_distant_targets": lambda r: "small_object_failure" in r["categories"] or "distant_target_unverifiable" in r["categories"],
            "source_label_review": lambda r: r["verification_status"] in {"incorrect_source_label", "unverifiable"},
        }
        for title, selector in sheet_specs.items():
            selected = [r for r in error_rows if selector(r)]
            panels = []
            for r in selected:
                idx = None if r["frame_index"] == "" else int(r["frame_index"])
                original = frame_image(ROOT / r["local_path"], idx)
                boxes = json.loads(r["prediction_boxes_json"])
                panels.append((original, boxes, f"{r['identifier']} | {r['verification_status']}"))
            for start in range(0, len(panels), 8):
                grid(panels[start:start+8], OUT / f"{title}_{start//8+1:02}.jpg")

    print(json.dumps({"media": len(predictions), "units": len(units), "threshold_summary": threshold, "decisions_loaded": DECISIONS.exists()}, indent=2))


if __name__ == "__main__":
    main()
