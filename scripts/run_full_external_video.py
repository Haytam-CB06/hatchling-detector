"""Run full-frame inference on the short, real leatherback beach clip."""

import json
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "artifacts" / "training" / "hatchling_n_640" / "weights" / "best.pt"
VIDEO = next((ROOT / "data" / "external_test" / "originals" / "videos").glob("leatherback_baby_turtle_running_to_sea_*.webm"))
OUT = ROOT / "artifacts" / "external_test" / "annotated_videos"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(MODEL))
    cap = cv2.VideoCapture(str(VIDEO))
    fps = cap.get(cv2.CAP_PROP_FPS) or 29.97
    cap.release()
    destination = OUT / "leatherback_full_annotated.mp4"
    writer = None
    predictions = []
    start = time.perf_counter()
    for index, result in enumerate(model.predict(source=str(VIDEO), stream=True, imgsz=640, conf=0.10,
                                                  device="cpu", verbose=False)):
        boxes = [{"confidence": round(float(b.conf.item()), 5),
                  "xyxy": [round(float(v), 2) for v in b.xyxy[0].tolist()]}
                 for b in result.boxes]
        predictions.append({"frame_index": index, "time_s": round(index / fps, 3), "boxes": boxes,
                            "inference_ms": result.speed.get("inference")})
        plotted = result.plot()
        if writer is None:
            writer = cv2.VideoWriter(str(destination), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                                     (plotted.shape[1], plotted.shape[0]))
            if not writer.isOpened():
                raise RuntimeError("Cannot open MP4 writer")
        writer.write(plotted)
        if (index + 1) % 100 == 0:
            print("processed", index + 1, flush=True)
    if writer:
        writer.release()
    (OUT / "leatherback_full_predictions.json").write_text(json.dumps(predictions, indent=2), encoding="utf-8")
    print("FULL VIDEO", len(predictions), "frames", round(time.perf_counter() - start, 2), "seconds")
    for threshold in (0.10, 0.25, 0.40):
        count = sum(any(b["confidence"] >= threshold for b in frame["boxes"]) for frame in predictions)
        print("frames with >=1 detection", threshold, count)


if __name__ == "__main__":
    main()
