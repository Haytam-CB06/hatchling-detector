"""Create a small train-split review queue and run baseline inference; never train."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from PIL import Image
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "generated" / "hatchling_yolo_v1"
CURATION = ROOT / "artifacts" / "dataset_audit" / "v24_split_curation.csv"
MODEL = ROOT / "artifacts" / "training" / "hatchling_n_640" / "weights" / "best.pt"
OUTPUT = ROOT / "artifacts" / "annotation_review" / "task03" / "training_pool"
EXCLUDED_GROUPS = {f"image:st-{number}_png" for number in range(32, 36)}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-class", type=int, default=24,
                        help="One image per source group: this many existing positive and negative candidates")
    args = parser.parse_args()
    if args.per_class < 1:
        parser.error("--per-class must be positive")
    manifest_path, prediction_path = OUTPUT / "manifest.csv", OUTPUT / "predictions.json"
    if manifest_path.exists() or prediction_path.exists():
        parser.error("Training review pool already exists; refusing to overwrite it")
    with CURATION.open(newline="", encoding="utf-8-sig") as stream:
        curation = {row["filename"]: row for row in csv.DictReader(stream)}
    candidates: dict[str, list[tuple[str, Path, str]]] = {"positive": [], "negative": []}
    used_groups: set[str] = set()
    for image in sorted((DATASET / "images" / "train").iterdir()):
        if image.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        row = curation.get(image.name)
        if not row or row["curated_split"] != "train":
            raise ValueError(f"Missing or inconsistent train curation row: {image.name}")
        group = row["group"]
        if group in EXCLUDED_GROUPS or group in used_groups:
            continue
        label = DATASET / "labels" / "train" / (image.stem + ".txt")
        if not label.is_file():
            raise ValueError(f"Missing label file: {label}")
        role = "positive" if label.read_text(encoding="utf-8").strip() else "negative"
        candidates[role].append((group, image, role))
        used_groups.add(group)
    selected = candidates["positive"][:args.per_class] + candidates["negative"][:args.per_class]
    if len(selected) < args.per_class * 2:
        parser.error("Not enough distinct groups for the requested balanced sample")
    model = YOLO(str(MODEL))
    output_rows, prediction_rows = [], []
    for group, image, role in selected:
        with Image.open(image) as decoded:
            width, height = decoded.size
            decoded.verify()
        result = model.predict(source=str(image), conf=0.10, imgsz=640, device="cpu", verbose=False)[0]
        boxes = [{"class_id": int(cls), "confidence": round(float(confidence), 6),
                  "xyxy": [round(float(value), 4) for value in coordinates]}
                 for coordinates, confidence, cls in zip(result.boxes.xyxy.tolist(),
                                                         result.boxes.conf.tolist(), result.boxes.cls.tolist())]
        relative = image.relative_to(ROOT).as_posix()
        output_rows.append({"title": image.name, "role": f"existing_label_{role}", "kind": "image",
                            "source_page": "", "group_id": group, "width": width, "height": height,
                            "local_path": relative, "sha256": digest(image)})
        prediction_rows.append({"media": relative, "kind": "image", "predictions": [{"boxes": boxes}]})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    prediction_path.write_text(json.dumps(prediction_rows, indent=2), encoding="utf-8")
    (OUTPUT / "provenance.json").write_text(json.dumps({
        "source_split": "curated train only", "selection": "sorted filename, first distinct source group per existing positive/negative label",
        "per_class": args.per_class, "excluded_known_cross_split_scene_groups": sorted(EXCLUDED_GROUPS),
        "confidence_floor": 0.10, "image_size": 640, "device": "cpu", "model_path": str(MODEL.relative_to(ROOT)),
        "model_sha256": digest(MODEL), "count": len(selected),
        "warning": "Existing labels are candidate sampling tags, not verified biological truth. No test/validation image is included."
    }, indent=2), encoding="utf-8")
    print(f"Wrote {len(output_rows)} training-eligible review candidates to {OUTPUT}")


if __name__ == "__main__":
    main()
