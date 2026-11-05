"""Local configuration for the detection studio."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "artifacts" / "training" / "hatchling_n_640" / "weights" / "best.pt"
MODEL_PATH = Path(os.environ.get("NAZAR_MODEL_PATH", str(DEFAULT_MODEL))).expanduser().resolve()
JOB_ROOT = Path(os.environ.get("NAZAR_JOB_DIR", str(ROOT / "artifacts" / "studio_jobs"))).expanduser().resolve()
REVIEW_MANIFEST = Path(os.environ.get("NAZAR_REVIEW_MANIFEST", str(ROOT / "data" / "external_test" / "manifests" / "combined_manifest.csv"))).expanduser().resolve()
REVIEW_PREDICTIONS = Path(os.environ.get("NAZAR_REVIEW_PREDICTIONS", str(ROOT / "artifacts" / "external_test" / "predictions.json"))).expanduser().resolve()
REVIEW_TRAIN_MANIFEST = Path(os.environ.get("NAZAR_REVIEW_TRAIN_MANIFEST", str(ROOT / "artifacts" / "annotation_review" / "task03" / "training_pool" / "manifest.csv"))).expanduser().resolve()
REVIEW_TRAIN_PREDICTIONS = Path(os.environ.get("NAZAR_REVIEW_TRAIN_PREDICTIONS", str(ROOT / "artifacts" / "annotation_review" / "task03" / "training_pool" / "predictions.json"))).expanduser().resolve()
REVIEW_DB = Path(os.environ.get("NAZAR_REVIEW_DB", str(ROOT / "artifacts" / "annotation_review" / "task03" / "reviews.sqlite3"))).expanduser().resolve()
REVIEW_EXPORTS = Path(os.environ.get("NAZAR_REVIEW_EXPORTS", str(ROOT / "artifacts" / "annotation_review" / "task03" / "exports"))).expanduser().resolve()
PLATFORM_ROOT = Path(os.environ.get("NAZAR_PLATFORM_ROOT", str(ROOT / "artifacts" / "platform"))).expanduser().resolve()
DEVICE = os.environ.get("NAZAR_DEVICE", "cpu")
IMAGE_SIZE = int(os.environ.get("NAZAR_IMAGE_SIZE", "640"))
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 150 * 1024 * 1024
MAX_VIDEO_SECONDS = 180
MAX_VIDEO_FRAMES = 5400
MAX_IMAGE_PIXELS = 50_000_000
JOB_TTL_SECONDS = 24 * 60 * 60
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}
