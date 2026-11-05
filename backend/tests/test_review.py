"""Functional review and export tests with isolated storage and real source images."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException

from backend.app import config
from backend.app.review import Box, ReviewInput, ReviewStore, create_review_router


def store_for(tmp_path: Path) -> ReviewStore:
    return ReviewStore(config.REVIEW_MANIFEST, config.REVIEW_PREDICTIONS,
                       tmp_path / "reviews.sqlite3", tmp_path / "exports",
                       config.REVIEW_TRAIN_MANIFEST, config.REVIEW_TRAIN_PREDICTIONS)


def test_full_review_edit_reopen_negative_and_export(tmp_path):
    store = store_for(tmp_path)
    assert len(store.list()) == 131
    positive = next(item for item in store.items.values() if item["pool"] == "training" and len(item["predictions"]) >= 2)
    negative = next(item for item in store.items.values() if item["pool"] == "training" and not item["predictions"])
    ambiguous = next(item for item in store.items.values() if item["pool"] == "evaluation")
    original_hash = hashlib.sha256(positive["path"].read_bytes()).hexdigest()
    prediction_hash = hashlib.sha256(config.REVIEW_PREDICTIONS.read_bytes()).hexdigest()
    image = store.get(positive["id"])
    assert image["status"] == "unreviewed" and image["revision"] == 0
    assert image["image_url"].endswith("/media")
    assert len(image["predictions"]) >= 2

    # Move and resize one candidate, delete the others, and add a missed hatchling.
    first = image["predictions"][0]
    x1, y1, x2, y2 = first["xyxy"]
    edited = Box(id=first["id"], prediction_id=first["prediction_id"], class_name="hatchling",
                 xyxy=(max(0, x1 - 1), max(0, y1 - 1), min(image["width"], x2 + 1), min(image["height"], y2 + 1)))
    added = Box(id="new-hatchling", class_name="hatchling", xyxy=(2, 2, 12, 12))
    saved = store.save(positive["id"], ReviewInput(status="verified_positive", reviewer="reviewer-test",
                                                    notes="Corrected, removed and added", revision=0, boxes=[edited, added]))
    assert saved["revision"] == 1 and len(saved["boxes"]) == 2
    history = store.history(positive["id"])
    assert history[0]["changes"]["added"] == ["new-hatchling"]
    assert image["predictions"][1]["id"] in history[0]["changes"]["removed"]
    assert first["id"] in history[0]["changes"]["modified"]
    with pytest.raises(HTTPException, match="Review changed"):
        store.save(positive["id"], ReviewInput(status="verified_positive", reviewer="reviewer-test", revision=0, boxes=[edited, added]))

    store.save(negative["id"], ReviewInput(status="verified_negative", reviewer="reviewer-test",
                                           notes="No hatchling visible", revision=0, boxes=[]))
    store.save(ambiguous["id"], ReviewInput(status="ambiguous", reviewer="reviewer-test",
                                            notes="Cannot confirm", revision=0, boxes=[]))
    reopened = store_for(tmp_path)
    reread = reopened.get(positive["id"])
    assert reread["status"] == "verified_positive" and reread["boxes"][1]["id"] == "new-hatchling"
    assert reopened.get(negative["id"])["status"] == "verified_negative"
    exported = reopened.export("training")
    folder = Path(exported["path"])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 2 and {row["image_id"] for row in manifest} == {positive["id"], negative["id"]}
    assert all(row["pool"] == "training" for row in manifest)
    assert exported["hatchling_boxes"] == 2
    label = folder / "labels" / f"{positive['id']}.txt"
    lines = label.read_text().strip().splitlines()
    assert len(lines) == 2
    values = [float(value) for value in lines[1].split()[1:]]
    assert values == pytest.approx([7 / positive["width"], 7 / positive["height"],
                                    10 / positive["width"], 10 / positive["height"]], abs=1e-11)
    assert (folder / "labels" / f"{negative['id']}.txt").read_text() == ""
    assert hashlib.sha256(positive["path"].read_bytes()).hexdigest() == original_hash
    assert hashlib.sha256(config.REVIEW_PREDICTIONS.read_bytes()).hexdigest() == prediction_hash


def test_validation_rejects_invalid_boxes_and_status(tmp_path):
    store = store_for(tmp_path)
    item = next(item for item in store.items.values() if item["pool"] == "training")
    def reject(status: str, boxes: list[Box]):
        with pytest.raises(HTTPException) as error:
            store.save(item["id"], ReviewInput(status=status, boxes=boxes, revision=0))
        assert error.value.status_code == 422

    reject("verified_positive", [])
    reject("unknown", [])
    reject("in_review", [Box(id="bad", class_name="hatchling", xyxy=(0, 0, item["width"] + 1, 10))])
    valid = Box(id="good", class_name="hatchling", xyxy=(0, 0, 10, 10))
    reject("verified_negative", [valid])
    reject("in_review", [valid, valid])
    adult = Box(id="adult", class_name="adult_turtle", xyxy=(0, 0, 10, 10))
    assert store.save(item["id"], ReviewInput(status="verified_negative", reviewer="reviewer-test", boxes=[adult], revision=0))["revision"] == 1
    assert store_for(tmp_path).get(item["id"])["boxes"][0]["class_name"] == "adult_turtle"
    exported = Path(store.export("training")["path"])
    assert next((exported / "labels").glob("*.txt")).read_text() == ""


def test_review_routes_are_registered(tmp_path):
    app = FastAPI()
    app.include_router(create_review_router(store_for(tmp_path)))
    paths = app.openapi()["paths"]
    assert "/api/review/images" in paths
    assert "put" in paths["/api/review/images/{image_id}"]
    assert "/api/review/images/{image_id}/media" in paths
    assert "/api/review/images/{image_id}/history" in paths
    assert "post" in paths["/api/review/exports"]


def test_frozen_evaluation_reviews_cannot_enter_training_export(tmp_path):
    store = store_for(tmp_path)
    evaluation = next(item for item in store.items.values() if item["pool"] == "evaluation")
    box = Box(id="human-1", class_name="hatchling", xyxy=(1, 1, 11, 11))
    store.save(evaluation["id"], ReviewInput(status="verified_positive", reviewer="reviewer-test", boxes=[box], revision=0))
    with pytest.raises(HTTPException, match="No verified training"):
        store.export("training")
    result = store.export("evaluation")
    assert result["purpose"] == "evaluation" and result["images"] == 1
    assert json.loads((Path(result["path"]) / "manifest.json").read_text())[0]["pool"] == "evaluation"


def test_export_boxes_touching_image_edges_stay_within_bounds(tmp_path):
    store = store_for(tmp_path)
    item = next(item for item in store.items.values() if item["pool"] == "training")
    box = Box(id="edge", class_name="hatchling", xyxy=(0, 0, item["width"], item["height"] - 1))
    store.save(item["id"], ReviewInput(status="verified_positive", reviewer="reviewer-test", boxes=[box], revision=0))
    exported = Path(store.export("training")["path"])
    line = (exported / "labels" / f"{item['id']}.txt").read_text().strip()
    _, x, y, w, h = line.split()
    x, y, w, h = map(Decimal, (x, y, w, h))
    assert Decimal(0) <= x - w / 2 < x + w / 2 <= Decimal(1)
    assert Decimal(0) <= y - h / 2 < y + h / 2 <= Decimal(1)
