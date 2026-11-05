"""One durable job per process. All commands are fixed Python entry points."""
from __future__ import annotations

import argparse
import json
import shutil
import traceback
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

from . import config
from .platform_data import bootstrap_catalog, inspect_dataset, prepare_version
from .platform_db import PlatformDB, digest, now, uid
from .platform_jobs import Jobs, hardware, register_model, scan_models, train_preflight
from .review import ReviewStore


class Cancelled(Exception):
    pass


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2-x1) * max(0, y2-y1)
    return intersection / max(1e-12, (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection)


def evaluation(db, payload, progress):
    model_row = db.one("SELECT * FROM platform_models WHERE id=?", (payload["model_id"],))
    version = db.one("SELECT * FROM platform_versions WHERE id=?", (payload["version_id"],))
    if not model_row or not version:
        raise ValueError("Registered model and dataset version required")
    if digest(config.ROOT / model_row["checkpoint"]) != model_row["sha256"]:
        raise ValueError("Checkpoint checksum mismatch")
    entries = [r for r in json.loads(version["manifest_json"]) if r["split"] == payload["split"]]
    if not entries or any(r["status"] not in {"verified_positive", "verified_negative"} for r in entries):
        raise ValueError("Evaluation requires a nonempty verified partition")
    for row in entries:
        if digest(Path(version["path"]) / row["image"]) != row["source_sha256"] or digest(Path(version["path"]) / row["label"]) != row["label_sha256"]:
            raise ValueError("Prepared evaluation files changed")
    run_id = uid()
    destination = db.root / "evaluations" / run_id
    model = YOLO(str(config.ROOT / model_row["checkpoint"]))
    metrics = model.val(data=str(Path(version["path"]) / "dataset.yaml"), split=payload["split"],
                        imgsz=payload["imgsz"], batch=1, device=payload["device"], conf=.001, iou=.7,
                        workers=0, plots=True, project=str(destination.parent), name=run_id, exist_ok=False, verbose=False)
    gallery = []
    for index, row in enumerate(entries):
        path = Path(version["path"]) / row["image"]
        result = model.predict(str(path), imgsz=payload["imgsz"], conf=payload["confidence"], iou=payload["iou"], device=payload["device"], verbose=False)[0]
        ground = [b for b in row["boxes"] if b["class_name"] == "hatchling"]
        matched = set()
        predictions = []
        categories = set()
        for predicted in result.boxes:
            box = predicted.xyxy[0].tolist()
            conf = float(predicted.conf.item())
            candidates = [(iou(box, truth["xyxy"]), n) for n, truth in enumerate(ground) if n not in matched]
            best, target = max(candidates, default=(0, -1))
            category = "correct_detection" if best >= .5 else "background_false_positive"
            if best >= .5:
                matched.add(target)
            else:
                for context in row["boxes"]:
                    if context["class_name"] in {"adult_turtle", "crab", "bird"} and iou(box, context["xyxy"]) >= .3:
                        category = context["class_name"] + "_confusion"
            if conf < .4:
                categories.add("low_confidence")
            categories.add(category)
            predictions.append({"xyxy": box, "confidence": conf, "category": category})
        missed = [b for n, b in enumerate(ground) if n not in matched]
        if missed:
            categories.add("missed_hatchling")
        image_name = f"{row['image_id']}.jpg"
        annotated = result.plot()
        for truth in missed:
            x1, y1, x2, y2 = map(int, truth["xyxy"])
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 0, 255), 3)
            cv2.putText(annotated, "missed GT", (x1, max(20, y1-5)), cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 0, 255), 2)
        cv2.imwrite(str(destination / image_name), annotated)
        gallery.append({"image_id": row["image_id"], "image": image_name, "categories": sorted(categories),
                        "predictions": predictions, "missed": missed, "tp": len(matched), "fp": len(predictions)-len(matched), "fn": len(missed)})
        progress(index+1, len(entries), "Matching predictions to verified annotations")
    scope = "validation" if payload["split"] == "val" else ("independent_test" if json.loads(version["summary_json"])["independent_test"] else "non_independent_test")
    result_json = {"precision": float(metrics.box.mp), "recall": float(metrics.box.mr), "map50": float(metrics.box.map50),
                   "map50_95": float(metrics.box.map), "speed": metrics.speed, "scope": scope, "matching_iou": .5,
                   "model_sha256": model_row["sha256"], "images": len(entries), "gallery": gallery,
                   "settings": payload, "software": hardware()["packages"]}
    (destination / "evaluation.json").write_text(json.dumps(result_json, indent=2), encoding="utf-8")
    db.execute("INSERT INTO platform_evaluations VALUES(?,?,?,?,?,?,?,?,?)", (run_id, model_row["id"], version["id"], payload["job_id"], now(), scope, json.dumps(payload), json.dumps(result_json), str(destination)))
    return {"evaluation_id": run_id, **{k: v for k, v in result_json.items() if k != "gallery"}}


def train(db, payload, jobs, job_id):
    check = train_preflight(db, payload)
    if not check["ready"]:
        raise ValueError("; ".join(check["errors"]))
    model_row = db.one("SELECT * FROM platform_models WHERE id=?", (payload["model_id"],))
    version = db.one("SELECT * FROM platform_versions WHERE id=?", (payload["version_id"],))
    checkpoint = config.ROOT / model_row["checkpoint"]
    model = YOLO(str(checkpoint))
    if model.task != "detect":
        raise ValueError("Only detection checkpoints are supported")
    destination = db.root / "experiments" / job_id
    if payload.get("resume_job_id"):
        previous = db.root / "experiments" / payload["resume_job_id"]
        previous_last = previous / "weights/resume.pt"
        if not previous_last.is_file(): previous_last = previous / "weights/last.pt"
        if not previous_last.is_file():
            raise ValueError("No resumable checkpoint was preserved")
        shutil.copytree(previous, destination)
        copied = destination / "weights" / previous_last.name
        state = torch.load(copied, map_location="cpu", weights_only=False)
        if state.get("optimizer") is None:
            raise ValueError("Checkpoint optimizer was stripped; choose fine-tuning instead of resume")
        state["train_args"].update({"project": str(destination.parent), "name": job_id, "save_dir": str(destination),
                                     "data": str(Path(version["path"]) / "dataset.yaml"), "epochs": payload["epochs"]})
        torch.save(state, copied)
        model = YOLO(str(copied))

    last_training_epoch = None

    def epoch_start(trainer):
        nonlocal last_training_epoch
        last_training_epoch = trainer.epoch

    def epoch_end(trainer):
        # Ultralytics also emits this callback during final evaluation with an
        # incremented epoch. That event must not replace an optimizer checkpoint
        # or appear as an extra training epoch in the application.
        if trainer.epoch != last_training_epoch:
            return
        metrics = {str(k): float(v) for k, v in (trainer.metrics or {}).items()}
        jobs.update(job_id, progress=min(100, (trainer.epoch+1)/payload['epochs']*100),
                    stage=f"Epoch {trainer.epoch+1} / {payload['epochs']}", result_json=json.dumps({"epoch": trainer.epoch+1, "metrics": metrics}))
        # The library's time budget can recalculate its epoch target. Both the
        # requested epoch bound and the runtime cap remain application limits.
        trainer.stop |= trainer.epoch + 1 >= payload['epochs']
        if db.one("SELECT cancel_requested FROM platform_jobs WHERE id=?", (job_id,))["cancel_requested"]:
            trainer.save_model()
            shutil.copyfile(trainer.last, Path(trainer.save_dir)/'weights/resume.pt')
            trainer.stop = True
    model.add_callback("on_train_epoch_start", epoch_start)
    model.add_callback("on_fit_epoch_end", epoch_end)
    model.train(data=str(Path(version["path"]) / "dataset.yaml"),
                epochs=payload["epochs"], imgsz=payload["imgsz"], batch=payload["batch"],
                optimizer=payload["optimizer"], lr0=payload["lr0"], device=payload["device"],
                patience=payload["patience"], seed=payload["seed"], mosaic=payload["mosaic"],
                time=payload["max_hours"], workers=0, deterministic=True, cache=False,
                project=str(destination.parent), name=job_id, exist_ok=bool(payload.get("resume_job_id")),
                resume=bool(payload.get("resume_job_id")), plots=True)
    ids = [register_model(db, p, version["id"], job_id) for p in (destination / "weights").glob("*.pt")]
    return {"models": ids, "version_id": version["id"], "checkpoint_initialization_sha256": model_row["sha256"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True); parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    db = PlatformDB(args.db, args.root); jobs = Jobs(db)
    row = jobs.get(args.job)
    if not row or row["status"] not in {"queued", "running"}:
        return
    payload = row["payload"]
    payload["job_id"] = args.job
    review = ReviewStore(config.REVIEW_MANIFEST, config.REVIEW_PREDICTIONS, db.path, config.REVIEW_EXPORTS,
                         config.REVIEW_TRAIN_MANIFEST, config.REVIEW_TRAIN_PREDICTIONS)
    def progress(current, total, stage):
        if db.one("SELECT cancel_requested FROM platform_jobs WHERE id=?", (args.job,))["cancel_requested"]:
            raise Cancelled("Stopped by user")
        jobs.update(args.job, progress=round(current/max(total, 1)*100, 2), stage=stage)
    jobs.update(args.job, status="running", stage="Starting")
    try:
        if db.one("SELECT cancel_requested FROM platform_jobs WHERE id=?",(args.job,))['cancel_requested']:
            raise Cancelled('Stopped before execution')
        if row["kind"] == "bootstrap":
            bootstrap_catalog(db, review); result = scan_models(db)
        elif row["kind"] == "inspect":
            result = inspect_dataset(db, payload["dataset_id"], progress)
        elif row["kind"] == "prepare":
            result = prepare_version(db, review, payload, progress)
        elif row["kind"] == "train":
            result = train(db, payload, jobs, args.job)
        elif row["kind"] == "evaluate":
            result = evaluation(db, payload, progress)
        elif row["kind"] == "report":
            from .platform_reports import create_report
            result = create_report(db, payload)
        elif row["kind"] == "extract_frames":
            dataset = db.one("SELECT * FROM platform_datasets WHERE id=?", (payload["dataset_id"],))
            directory = Path(dataset["root_path"])
            source = directory / payload["filename"]
            cap = cv2.VideoCapture(str(source))
            fps = cap.get(cv2.CAP_PROP_FPS)
            if not cap.isOpened() or not 0<cap.get(cv2.CAP_PROP_FRAME_WIDTH)*cap.get(cv2.CAP_PROP_FRAME_HEIGHT)<=50_000_000:
                cap.release();raise ValueError('Video cannot be decoded within the 50-megapixel frame limit')
            count, kept = 0, 0
            output = directory / "images"; output.mkdir(exist_ok=True)
            while cap.isOpened() and kept < min(payload["max_frames"], 500):
                ok, frame = cap.read()
                if not ok: break
                if count % payload["stride"] == 0:
                    ok,encoded=cv2.imencode('.jpg',frame)
                    if not ok or len(encoded)>max(0,shutil.disk_usage(output).free-64_000_000):
                        cap.release();raise ValueError('Insufficient storage for extracted frames')
                    (output/f'frame_{count:08d}.jpg').write_bytes(encoded.tobytes()); kept += 1
                count += 1
                progress(kept, payload["max_frames"], "Extracting video frames")
            cap.release()
            if not kept: raise ValueError("No decodable frames")
            result = inspect_dataset(db, dataset["id"], progress)
            recording = "recording:" + digest(source)
            db.execute("UPDATE platform_images SET source_group=?,metadata_json=? WHERE dataset_id=?", (recording, json.dumps({"recording_sha256": digest(source), "source_video": source.name, "fps": fps, "stride": payload["stride"]}), dataset["id"]))
            saved_frames=directory.parent/'source_frame_predictions.json'
            if saved_frames.is_file():
                frame_predictions={r['frame']:r['detections'] for r in json.loads(saved_frames.read_text(encoding='utf-8'))}
                for image in db.all('SELECT id,filename FROM platform_images WHERE dataset_id=?',(dataset['id'],)):
                    frame_number=int(Path(image['filename']).stem.split('_')[-1])
                    boxes=[{'id':f'prediction-{n}','prediction_id':f'prediction-{n}','class_name':b['class_name'],'confidence':b['confidence'],'xyxy':b['box_xyxy']} for n,b in enumerate(frame_predictions.get(frame_number,[]))]
                    db.execute('UPDATE platform_images SET predictions_json=? WHERE id=?',(json.dumps(boxes),image['id']))
        elif row["kind"] == "registry_scan":
            result = scan_models(db)
        elif row["kind"] == "suggest":
            checkpoint = db.one("SELECT * FROM platform_models WHERE id=?", (payload["model_id"],))
            if not checkpoint or digest(config.ROOT / checkpoint["checkpoint"]) != checkpoint["sha256"]:
                raise ValueError("A valid registered model is required")
            model = YOLO(str(config.ROOT / checkpoint["checkpoint"]))
            images = db.all("SELECT * FROM platform_images WHERE dataset_id=?", (payload["dataset_id"],))
            records = []
            for index, image in enumerate(images):
                prediction = model.predict(str(config.ROOT / image["path"]), conf=.10, imgsz=640, device="cpu", verbose=False)[0]
                boxes = [{"id": f"suggestion-{n}", "class_name": str(model.names[int(box.cls.item())]), "xyxy": box.xyxy[0].tolist(), "confidence": float(box.conf.item())} for n, box in enumerate(prediction.boxes)]
                db.execute("INSERT INTO platform_suggestions VALUES(?,?,?,?,?,?)", (uid(), image["id"], checkpoint["id"], args.job, json.dumps(boxes), now()))
                records.append({"image_id": image["id"], "boxes": boxes})
                progress(index+1, len(images), "Generating unverified suggestions")
            folder = db.root / "predictions"; folder.mkdir(exist_ok=True)
            (folder / f"{args.job}.json").write_text(json.dumps(records), encoding="utf-8")
            result = {"images": len(images), "model_sha256": checkpoint["sha256"], "approval": "none; human review required"}
        else:
            raise ValueError("Unsupported job type")
        stopped = db.one("SELECT cancel_requested FROM platform_jobs WHERE id=?", (args.job,))["cancel_requested"]
        jobs.update(args.job, status="stopped" if stopped else "completed", stage="Stopped" if stopped else "Completed", progress=100, result_json=json.dumps(result))
    except Cancelled as exc:
        jobs.update(args.job, status="stopped", stage="Stopped", error=str(exc))
        if payload.get('dataset_id') and row['kind'] in {'inspect','extract_frames'}:
            db.execute("UPDATE platform_datasets SET state='stopped' WHERE id=?",(payload['dataset_id'],))
    except Exception as exc:
        traceback.print_exc()
        jobs.update(args.job, status="failed", stage="Failed", error=str(exc)[:2000])
        if payload.get('dataset_id') and row['kind'] in {'inspect','extract_frames'}:
            db.execute("UPDATE platform_datasets SET state='failed' WHERE id=?",(payload['dataset_id'],))


if __name__ == "__main__":
    main()
