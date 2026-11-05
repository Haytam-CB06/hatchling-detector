"""Reproducible exploratory inference on the external media collection.

The files do not have ground-truth bounding boxes, so this script deliberately
reports detections and review candidates, not precision/recall or mAP.
"""

from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import torch
import ultralytics
from PIL import Image, ImageDraw, ImageOps
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "external_test"
ART = ROOT / "artifacts" / "external_test"
MODEL = ROOT / "artifacts" / "training" / "hatchling_n_640" / "weights" / "best.pt"
THRESHOLDS = (0.10, 0.25, 0.40)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dhash(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    pixels = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = pixels[:, 1:] > pixels[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming(a, b):
    return (a ^ b).bit_count()


def train_fingerprints():
    images = list((ROOT / "data" / "generated" / "hatchling_yolo_v1").rglob("*.jpg"))
    exact = {}
    visual = []
    for path in images:
        image = cv2.imread(str(path))
        if image is None:
            continue
        exact[sha256(path)] = str(path.relative_to(ROOT))
        visual.append((dhash(image), str(path.relative_to(ROOT))))
    return exact, visual


def fingerprints_for(record, exact, visual):
    path = ROOT / record["local_path"]
    if record["kind"] != "image":
        return {"exact_train_match": "", "closest_train_dhash_distance": "", "closest_train_image": ""}
    im = cv2.imread(str(path))
    d = dhash(im)
    nearest = min(((hamming(d, h), p) for h, p in visual), default=(None, ""))
    return {"exact_train_match": exact.get(record["sha256"], ""),
            "closest_train_dhash_distance": nearest[0],
            "closest_train_image": nearest[1] if nearest[0] is not None and nearest[0] <= 8 else ""}


def predictions(result, frame_index=None, time_s=None):
    items = []
    for box in result.boxes:
        items.append({"class_id": int(box.cls.item()), "confidence": round(float(box.conf.item()), 5),
                      "xyxy": [round(float(v), 2) for v in box.xyxy[0].tolist()]})
    return {"frame_index": frame_index, "time_s": time_s, "boxes": items,
            "speed_ms": result.speed}


def result_counts(preds):
    return {str(t): sum(any(b["confidence"] >= t for b in p["boxes"]) for p in preds) for t in THRESHOLDS}


def draw_sheet(rows, path, title):
    if not rows:
        return
    cols = 4
    tile_w, tile_h = 320, 250
    display = rows[:40]
    canvas = Image.new("RGB", (cols * tile_w, ((len(display) + cols - 1) // cols) * tile_h + 40), "#eef1f3")
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 10), title, fill="#101820")
    for i, row in enumerate(display):
        im = Image.open(row["path"]).convert("RGB")
        im.thumbnail((tile_w - 16, tile_h - 55))
        x = (i % cols) * tile_w + 8
        y = (i // cols) * tile_h + 40
        canvas.paste(im, (x, y))
        draw.text((x, y + tile_h - 48), row["label"][:46], fill="#101820")
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, quality=85)


def load_manifest():
    return json.loads((DATA / "manifests" / "combined_manifest.json").read_text(encoding="utf-8"))


def main():
    if not MODEL.exists():
        raise FileNotFoundError(MODEL)
    ART.mkdir(parents=True, exist_ok=True)
    records = load_manifest()
    model = YOLO(str(MODEL))
    exact, visual = train_fingerprints()
    all_predictions = []
    summaries = []
    candidates = {"positive_source_no_detection": [], "negative_source_detection": [], "positive_source_detection": []}
    start = time.perf_counter()
    for i, record in enumerate(records, 1):
        path = ROOT / record["local_path"]
        short_id = hashlib.sha1(record["local_path"].encode()).hexdigest()[:10]
        print(f"{i}/{len(records)} {record['local_path']}", flush=True)
        leak = fingerprints_for(record, exact, visual)
        preds = []
        preview = ""
        if record["kind"] == "image":
            im = cv2.imread(str(path))
            result = model.predict(im, imgsz=640, conf=0.10, device="cpu", verbose=False)[0]
            pred = predictions(result)
            preds.append(pred)
            target = ART / "annotated_images" / f"{short_id}.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(target), result.plot())
            preview = str(target.relative_to(ROOT))
            key = ("positive_source_detection" if pred["boxes"] else "positive_source_no_detection") if record["role"] == "positive" else ("negative_source_detection" if pred["boxes"] else None)
            if key:
                candidates[key].append({"path": target, "label": f"{record['title'][:34]} | {len(pred['boxes'])} boxes"})
        else:
            cap = cv2.VideoCapture(str(path))
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total / fps if fps else 0
            count = min(24, max(1, int(duration) + 1))
            indices = sorted(set(np.linspace(0, max(total - 1, 0), count, dtype=int).tolist()))
            preview_dir = ART / "annotated_videos"
            preview_dir.mkdir(parents=True, exist_ok=True)
            video_path = preview_dir / f"{short_id}_sampled.mp4"
            writer = None
            for index in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                if not ok:
                    continue
                result = model.predict(frame, imgsz=640, conf=0.10, device="cpu", verbose=False)[0]
                preds.append(predictions(result, index, round(index / fps, 3)))
                plotted = result.plot()
                if writer is None:
                    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 1.0,
                                             (plotted.shape[1], plotted.shape[0]))
                writer.write(plotted)
            if writer is not None:
                writer.release()
                preview = str(video_path.relative_to(ROOT))
            cap.release()
        counts = result_counts(preds)
        summary = {"title": record["title"], "role": record["role"], "kind": record["kind"],
                   "local_path": record["local_path"], "source_page": record["source_page"],
                   "sampled_frames": len(preds), "frames_with_detection_at_0_10": counts["0.1"],
                   "frames_with_detection_at_0_25": counts["0.25"],
                   "frames_with_detection_at_0_40": counts["0.4"],
                   "total_boxes_at_0_10": sum(len(p["boxes"]) for p in preds),
                   "mean_inference_ms": round(np.mean([p["speed_ms"].get("inference", 0) for p in preds]), 2) if preds else None,
                   "preview": preview, **leak}
        summaries.append(summary)
        all_predictions.append({"media": record["local_path"], "role": record["role"], "kind": record["kind"],
                                "sampling": "single image" if record["kind"] == "image" else "up to 24 evenly spaced frames, sampled output at 1 fps",
                                "predictions": preds})
    (ART / "predictions.json").write_text(json.dumps(all_predictions, indent=2), encoding="utf-8")
    (ART / "run_summary.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    if summaries:
        with (ART / "run_summary.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(summaries[0]))
            w.writeheader(); w.writerows(summaries)
    for key, rows in candidates.items():
        draw_sheet(rows, ART / f"contact_{key}.jpg", key.replace("_", " "))
    metadata = {"model": str(MODEL.relative_to(ROOT)), "model_sha256": sha256(MODEL),
                "imgsz": 640, "base_confidence": 0.10, "thresholds": THRESHOLDS, "device": "cpu",
                "python": sys.version, "platform": platform.platform(), "ultralytics": ultralytics.__version__,
                "torch": torch.__version__, "opencv": cv2.__version__, "media_count": len(records),
                "training_images_fingerprinted": len(visual), "elapsed_seconds": round(time.perf_counter() - start, 2),
                "command": "conda run -n nazar-vision python scripts/evaluate_external_test.py"}
    (ART / "run_metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    print("DONE", json.dumps({"media": len(records), "elapsed_s": metadata["elapsed_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
