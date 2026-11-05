"""Focused checks for the read-only dataset audit helpers."""

from pathlib import Path
import sys

import numpy as np
from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from audit_task01_model_dataset import group_key, inspect_labels, read_image  # noqa: E402


def test_group_key_keeps_roboflow_variants_and_video_frames_together():
    assert group_key("st-10_jpg.rf.abc.jpg") == group_key("st-10_jpg.rf.def.jpg")
    assert group_key("vid11_mp4-1_jpg.rf.abc.jpg") == group_key("vid11_mp4-9_jpg.rf.def.jpg")
    assert group_key("st-10_jpg.rf.abc.jpg") != group_key("st-11_jpg.rf.abc.jpg")


def test_label_reader_flags_invalid_rows_without_dropping_valid_boxes(tmp_path):
    label = tmp_path / "sample.txt"
    label.write_text("0 0.5 0.5 1 1\n0 0.98 0.5 0.1 0.2\n1 0.5 0.5 0.2 0.2\n"
                     "0 nan 0.5 0.2 0.2\n0 0.1 0.1\n", encoding="utf-8")
    boxes, issues = inspect_labels(label, {0})
    assert len(boxes) == 1
    assert {issue["issue"] for issue in issues} == {
        "invalid_box_coordinate", "invalid_class_id", "non_finite_coordinate", "wrong_column_count"
    }


def test_resized_copy_is_not_exact_but_remains_perceptually_related(tmp_path):
    pixels = np.zeros((64, 96, 3), dtype=np.uint8)
    pixels[12:51, 21:73] = [180, 100, 50]
    pixels[25:41, 33:58] = [30, 210, 80]
    first, second = tmp_path / "first.png", tmp_path / "second.png"
    Image.fromarray(pixels).save(first)
    Image.fromarray(pixels).resize((192, 128), Image.Resampling.NEAREST).save(second)
    a, b = read_image(first), read_image(second)
    assert a["pixel_sha256"] != b["pixel_sha256"]
    assert (a["phash"] ^ b["phash"]).bit_count() <= 8
