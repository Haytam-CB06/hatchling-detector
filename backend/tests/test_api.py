"""API contract tests and a small real-checkpoint end-to-end smoke test."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.video_service import ffmpeg_executable


ROOT = Path(__file__).resolve().parents[2]


def wait_for_model(client: TestClient, state: str = "ready") -> dict:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        info = client.get("/api/model/info").json()
        if info["state"] == state:
            return info
        time.sleep(0.25)
    pytest.fail(f"Model did not reach {state}: {info}")


@pytest.fixture(scope="module")
def live_client(tmp_path_factory):
    directory = tmp_path_factory.mktemp("studio")
    app = create_app(job_root=directory / "studio_jobs", review_db=directory / "reviews.sqlite3",
                     review_exports=directory / "exports", platform_root=directory / "platform", bootstrap_platform=False)
    with TestClient(app) as client:
        assert wait_for_model(client)["classes"] == {"0": "hatchling"}
        yield client


def test_health_and_model_info(live_client):
    health = live_client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["model_state"] == "ready"
    assert health.json()["video_encoding_ready"] is True
    info = live_client.get("/api/model/info").json()
    assert info["ready"] and info["device"] == "cpu" and info["image_size"] == 640


def test_real_image_inference_download_and_serialization(live_client):
    image = ROOT / "backend/tests/fixtures/hatchling_nps.jpg"
    with image.open("rb") as stream:
        response = live_client.post("/api/detect/image", files={"file": (image.name, stream, "image/jpeg")},
                                    data={"confidence": "0.10", "iou": "0.45"})
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["status"] == "completed" and job["stats"]["object_count"] >= 1
    assert job['stage']=='completed'
    box = job["detections"][0]
    assert box["class_name"] == "hatchling" and 0 < box["confidence"] <= 1
    x1, y1, x2, y2 = box["box_xyxy"]
    assert 0 <= x1 < x2 <= job["stats"]["width"]
    assert 0 <= y1 < y2 <= job["stats"]["height"]
    result = live_client.get(job["result_url"])
    assert result.status_code == 200 and result.headers["content-type"].startswith("image/png")
    output = cv2.imdecode(np.frombuffer(result.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert output is not None and output.shape[:2] == (job["stats"]["height"], job["stats"]["width"])
    download = live_client.get(job["download_url"])
    assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]
    candidate = live_client.post('/api/platform/active-learning/candidates', json={'job_id':job['job_id'],'name':'Isolated active-learning candidate'})
    assert candidate.status_code == 202, candidate.text
    deadline = time.monotonic()+90
    while time.monotonic()<deadline:
        imported = live_client.get('/api/platform/jobs/'+candidate.json()['job']['id']).json()
        if imported['status'] in {'completed','failed','interrupted'}:break
        time.sleep(.2)
    assert imported['status']=='completed', imported
    queued = live_client.get('/api/platform/datasets/'+candidate.json()['dataset_id']).json()['images']
    assert len(queued)==1 and queued[0]['status']=='unreviewed'
    assert len(queued[0]['predictions'])==len(job['detections'])


def test_no_detection_and_bad_uploads(live_client):
    blank = np.full((180, 320, 3), 255, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", blank)
    assert ok
    result = live_client.post("/api/detect/image", files={"file": ("empty.png", encoded.tobytes(), "image/png")},
                              data={"confidence": "0.95"})
    assert result.status_code == 200
    assert result.json()["stats"]["object_count"] == 0
    rendered = live_client.get(result.json()["result_url"])
    decoded = cv2.imdecode(np.frombuffer(rendered.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert np.array_equal(decoded, blank)
    unsupported = live_client.post("/api/detect/image", files={"file": ("notes.txt", b"text", "text/plain")})
    assert unsupported.status_code == 415
    corrupt = live_client.post("/api/detect/image", files={"file": ("broken.jpg", b"not an image", "image/jpeg")})
    assert corrupt.status_code == 400


def test_real_video_job_and_playable_output(live_client, tmp_path):
    source = ROOT / "data/video/real_leatherback_demo.mp4"
    cap = cv2.VideoCapture(str(source))
    sample = tmp_path / "real_hatchling_sample.mp4"
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(sample), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (width, height))
    for _ in range(12):
        ok, frame = cap.read()
        assert ok
        writer.write(frame)
    cap.release(); writer.release()
    with sample.open("rb") as stream:
        response = live_client.post("/api/detect/video", files={"file": (sample.name, stream, "video/mp4")},
                                    data={"confidence": "0.10", "iou": "0.45"})
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        job = live_client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.25)
    assert job["status"] == "completed", job
    assert job["processed_frames"] == 12
    assert job["stats"]["frame_level_detection_instances"] >= 0
    result = live_client.get(job["result_url"])
    assert result.status_code == 200 and result.headers["content-type"].startswith("video/mp4")
    output = tmp_path / "output.mp4"
    output.write_bytes(result.content)
    reader = cv2.VideoCapture(str(output))
    assert reader.isOpened() and int(reader.get(cv2.CAP_PROP_FRAME_COUNT)) == 12
    assert abs(reader.get(cv2.CAP_PROP_FPS) - 10) < 0.2
    ok, frame = reader.read()
    assert ok and frame.shape[:2] == (height, width)
    reader.release()
    download = live_client.get(job["download_url"])
    assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]


def test_audio_is_retained_when_present(live_client, tmp_path):
    ffmpeg = ffmpeg_executable()
    assert ffmpeg is not None
    sample = tmp_path / "real_footage_with_test_audio.mp4"
    source = ROOT / "data/video/real_leatherback_demo.mp4"
    create = subprocess.run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                             "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-t", "1",
                             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                             "-shortest", str(sample)], capture_output=True, text=True, timeout=60)
    assert create.returncode == 0, create.stderr
    with sample.open("rb") as stream:
        response = live_client.post("/api/detect/video", files={"file": (sample.name, stream, "video/mp4")})
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        job = live_client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.25)
    assert job["status"] == "completed", job
    assert job["stats"]["audio"] == "AAC audio included"
    output = tmp_path / "annotated_with_audio.mp4"
    output.write_bytes(live_client.get(job["result_url"]).content)
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(output)],
                           capture_output=True, text=True, timeout=30)
    assert "Audio: aac" in probe.stderr


def test_missing_model_and_result_state(tmp_path):
    app = create_app(model_path=tmp_path / "missing.pt", job_root=tmp_path / "jobs", review_db=tmp_path / "reviews.sqlite3",
                     review_exports=tmp_path / "exports", platform_root=tmp_path / "platform", bootstrap_platform=False)
    with TestClient(app) as client:
        info = wait_for_model(client, "unavailable")
        assert not info["ready"] and "do not exist" in info["reason"]
        image = client.post("/api/detect/image", files={"file": ("x.png", b"invalid", "image/png")})
        assert image.status_code == 503
        assert client.get("/api/jobs/not-a-job").status_code == 404
        assert client.get("/api/jobs/not-a-job/result").status_code == 404


def test_expired_file_cleanup(live_client):
    store = live_client.app.state.jobs
    job_id, directory = __import__("backend.app.storage", fromlist=["new_job_dir"]).new_job_dir(store.root)
    (directory / "annotated.png").write_bytes(b"test")
    store.add(job_id, "image")
    store._jobs[job_id]["created_at"] = 0
    store.expire()
    assert not directory.exists()
    assert live_client.get(f"/api/jobs/{job_id}").status_code == 404
