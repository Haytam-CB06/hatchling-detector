"""Real Ultralytics checkpoint adapter. Calls are serialized by the API worker."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from .platform_db import digest


class ModelUnavailable(RuntimeError):
    pass


class ModelService:
    def __init__(self, path: Path, device: str, image_size: int):
        self.path = path
        self.device = device
        self.image_size = image_size
        self._model: YOLO | None = None
        self._state = "loading"
        self._reason = ""
        self._sha256 = ""
        self.expected_sha = None
        self._lock = threading.Lock()

    def load(self) -> None:
        try:
            self.activate(self.path, self.expected_sha)
        except Exception as exc:
            with self._lock:
                self._state = "unavailable"
                self._reason = str(exc) if isinstance(exc, (FileNotFoundError, ValueError)) else "Model could not be loaded"

    def activate(self, path: Path, expected_sha: str | None = None):
        if not path.is_file():
            raise FileNotFoundError("Configured model weights do not exist")
        sha = digest(path)
        if expected_sha and sha != expected_sha:
            raise ValueError("Checkpoint checksum mismatch")
        model = YOLO(str(path))
        if model.task != "detect":
            raise ValueError("Configured checkpoint is not an object detector")
        if set(model.names.values()) != {"hatchling"}:
            raise ValueError("Active inference requires a trained one-class hatchling detector")
        model.predict(np.zeros((self.image_size, self.image_size, 3), dtype=np.uint8),
                      conf=.25, imgsz=self.image_size, device=self.device, verbose=False)
        with self._lock:
            self.path = path
            self._model, self._state, self._reason, self._sha256 = model, "ready", "", sha

    def info(self) -> dict:
        with self._lock:
            names = dict(self._model.names) if self._model is not None else {}
            return {
                "state": self._state,
                "ready": self._state == "ready",
                "reason": self._reason,
                "model_name": self.path.name,
                "sha256": self._sha256,
                "architecture": "Ultralytics YOLO26 object detection" if self._model is not None else None,
                "classes": names,
                "device": self.device,
                "image_size": self.image_size,
                "input": "BGR image/frame; Ultralytics letterboxing and NMS; coordinates returned in original pixels",
            }

    def predict(self, frame: np.ndarray, confidence: float, iou: float):
        model = self._model
        if model is None:
            raise ModelUnavailable("Model is not ready")
        start = time.perf_counter()
        result = model.predict(frame, conf=confidence, iou=iou, imgsz=self.image_size,
                               device=self.device, verbose=False)[0]
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        detections = []
        for box in result.boxes:
            class_id = int(box.cls.item())
            detections.append({
                "class_id": class_id,
                "class_name": str(model.names[class_id]),
                "confidence": round(float(box.conf.item()), 5),
                "box_xyxy": [round(float(v), 2) for v in box.xyxy[0].tolist()],
            })
        # plot() uses result.orig_img and boxes already mapped to original pixel coordinates.
        return result.plot(labels=True, conf=True), detections, elapsed_ms
