"""Replay validation for the existing best.pt on the current frozen export.

This is inference/evaluation only. It never trains or writes model/dataset files.
Outputs are contained in artifacts/model_improvement/task01_audit/.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/model_improvement/task01_audit"
MODEL = ROOT / "artifacts/training/hatchling_n_640/weights/best.pt"
DATA = ROOT / "data/generated/hatchling_yolo_v1/dataset.yaml"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before_hash = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    model = YOLO(str(MODEL))
    metrics = model.val(data=str(DATA), split="val", imgsz=640, batch=4,
                        device="cpu", workers=0, conf=0.001, iou=0.7,
                        plots=False, save_json=False, save_txt=False,
                        project=str(OUTPUT), name="checkpoint_val_replay", exist_ok=True,
                        verbose=False)
    after_hash = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    if before_hash != after_hash:
        raise RuntimeError("Checkpoint changed during read-only validation")
    inventory = json.loads((OUTPUT / "dataset_summary.json").read_text(encoding="utf-8"))
    result = {"model": str(MODEL), "model_sha256": after_hash,
              "dataset_yaml": str(DATA), "split": "val", "imgsz": 640,
              "batch": 4, "device": "cpu", "conf": 0.001, "iou": 0.7,
              "precision": float(metrics.box.mp), "recall": float(metrics.box.mr),
              "map50": float(metrics.box.map50), "map50_95": float(metrics.box.map),
              "validation_split_images_in_audit": inventory["splits"]["val"]["images"],
              "note": "Ultralytics aggregate validation metrics; not an independent field test"}
    # The count is from the independently enumerated audit, not the confusion
    # matrix, which counts detections rather than images.
    (OUTPUT / "checkpoint_val_replay.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
