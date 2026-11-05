# Nazar Vision model lifecycle platform

## Start the application

Open PowerShell in the project folder and activate the existing environment:

```powershell
conda activate nazar-vision
python -m pip install -r backend/requirements.txt
python -s -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second PowerShell terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5050/**. Vite uses port 5050 with strict port selection and proxies `/api` to port 8000. API documentation is at **http://127.0.0.1:8000/docs**. The backend and all workers use the activated Conda interpreter. No extra queue server or database server is required.

## Workflow

1. **Dataset library:** provide a name, source information, source classes, and intended pool. Choose individual files, a browser-selected directory, a ZIP archive, or one video. A new import directory preserves the uploaded files. Dataset YAML class names take precedence over the class list. Imports are never merged automatically. Videos create ordered frame candidates sharing a recording checksum.
2. **Quality control:** inspect decoding, labels, class IDs, finite/in-bounds boxes, exact/perceptual duplicates, source overlaps, and unusually sized boxes. Source findings remain visible after annotation corrections. They are not automatic deletion instructions. A suspected frozen-source match needs a reviewer and provenance evidence; exact frozen matches remain protected.
3. **Annotation review:** filter by dataset/pool/status, inspect source media and model confidence, draw/move/resize/delete boxes, correct the class, and choose a decision. Zoom is available from 50–300%. Delete removes the selected box, Escape deselects, and Ctrl+S saves. New approvals/rejections/exclusions require a reviewer name. Negative approvals contain no hatchling boxes. Ambiguous, needs-correction, rejected, and excluded decisions stay outside training exports. Original source labels, prediction records, and every saved annotation revision are preserved. Existing legacy approvals without a reviewer name are retained as recorded.
4. **Dataset approval:** the library can mark a dataset's decisions complete only when every image is approved, rejected, or excluded. The preparation wizard can also use an explicitly selected approved subset. Dataset approval does not claim source independence.
5. **Dataset preparation:** select approved samples and review the `hatchling → class 0` mapping. Supply a recording/wildlife-event ID, evidence, reviewer, and partition for each selected sample. Filename placeholders cannot be confirmed as source events. Frozen evaluation images may only be test samples. The preparation job rechecks source hashes, box validity, group consistency, exact/perceptual overlap, and bounded ORB/RANSAC crop/scene candidates before writing a new version. The output includes copied images, normalized YOLO labels, annotation revisions, label/image checksums, manifest, YAML, and integrity findings. Test independence remains unverified unless the provenance attestations and overlap checks support it; known baseline-source duplicates do not become independent evidence.
6. **Model training:** select a prepared version and an available local checkpoint. Configure image size, epochs, batch, learning rate, optimizer, device, mosaic, early stopping, seed, and runtime cap. A readiness check validates data checksums, available compute, and settings. The explicit resource checkbox authorizes the job. Training runs outside the HTTP request and writes a new experiment directory. Progress and charts come from recorded epochs and actual CSV metrics. Stop requests are checked after an epoch; resumable optimizer checkpoints are preserved when supported. A resumed run copies the prior run into a new directory. The original run is retained.
7. **Model registry:** inspect checkpoint hashes, file size, dataset/configuration, recorded timestamp, and actual logged validation metrics. Compare recorded values with their stated scope. Activating a trained one-class detector verifies its hash, loads it in the inference worker, and persists the selection. Pretrained weights initialize experiments and cannot masquerade as a trained hatchling deployment. Downloaded and previously registered checkpoints are not overwritten.
8. **Evaluation:** choose a trained model and verified immutable dataset partition. Ultralytics produces precision, recall, mAP50, mAP50:95, PR curves, confusion matrix, and timing. Separate image prediction matching at IoU 0.50 builds the error gallery. Adult/crab/bird confusion is labeled only when an approved contextual box supports it. Frozen tests use the predeclared deployment thresholds for the gallery, and are not a threshold exploration tool. Validation and non-independent test runs are labeled accordingly.
9. **Image & video inference:** select an active model, upload actual media, set confidence/IoU, and run detection. Boxes, labels, confidence, previews, and downloads use real predictions. Zero detections produce an explicit message. Video processing preserves frame order and dimensions and produces a browser-playable MP4. Counts across frames are detection instances, not unique turtles.
10. **Active learning:** send a completed inference source into a new candidate import. Images retain unverified prediction suggestions. Extracted video frames remain unreviewed until the reviewer corrects and approves them. The candidate then follows the same grouping/preparation workflow. Expired inference uploads must be uploaded again; the browser reports this explicitly.
11. **Video monitoring:** inspect actual uploaded-recording timelines and speed. The live-camera boundary is documented and explicitly unavailable. No camera is accessed.
12. **Reports & history:** generate persistent PDF, CSV, and JSON records for datasets, annotations, preparation, training, models, evaluation, inference, and comparisons. The older Task 1–3 evidence remains downloadable. Reports retain dataset/model identifiers, checksums, settings, software versions, and generation time.

Use **Load source label candidates** to restore the editable copy from the imported labels. **Load latest unverified model suggestions** uses the most recent saved suggestions instead. Both actions keep the review unapproved until you explicitly choose and save an approval.

The Reports page includes background-job history and recorded source/model decisions. Expand an event to inspect its stored evidence.

## Current project handover

The catalog contains 694 baseline images plus 83 frozen external still images. Eight saved reviews remain approved (seven positive, one negative; nine hatchling boxes). Other source labels are candidates, not new human approvals. Source groups and new dataset partitions still require your evidence and decisions; no scientific training version has been generated automatically.

The registry selection observed during handover is `hatchling_smoke_v1 / best`. To test the main baseline, open **Model registry**, find **hatchling_n_640 / best**, and select **Activate**. Activation verifies the saved checkpoint hash. All original checkpoints remain available.

## Storage and preservation

- Existing review database: `artifacts/annotation_review/task03/reviews.sqlite3`. Additive platform tables share the database; `reviews` and `review_events` retain their original records. New migration backups are under `artifacts/platform/backups/`.
- Original dataset inputs: `data/source/`, `data/generated/hatchling_yolo_v1/`, and `data/external_test/`. Catalog indexing reads them in place; it does not approve their source labels.
- Uploaded originals: `artifacts/platform/imports/<dataset-id>/raw/`.
- Reviewed version outputs: `data/processed/nazar_<version>/`.
- Background jobs/logs: `artifacts/platform/jobs/<job-id>/` and the `platform_jobs` table.
- New training runs: `artifacts/platform/experiments/<job-id>/`. The baseline at `artifacts/training/hatchling_n_640/weights/best.pt` is preserved.
- Evaluation artifacts: `artifacts/platform/evaluations/<run-id>/`.
- Reports: `artifacts/platform/reports/<report-id>/`.
- Inference outputs: `artifacts/studio_jobs/<job-id>/`; uploaded copies expire through the existing 24-hour cleanup. Persistent summaries remain in `artifacts/inference_history/`. Create a candidate import before the source expires if it should enter the review lifecycle.

## Reliability and deployment scope

The application is a local research platform bound to loopback, with one training/evaluation compute job at a time. SQLite stores durable jobs and subprocess IDs. Interrupted workers are reported as interrupted and retain logs/artifacts. Safe jobs may be retried; training needs an explicit new experiment or a supported resume. Uploads are bounded, archive paths and links are checked, workers use argument lists without a shell, and training parameters cannot inject commands. Free disk space and memory are checked before training.

The source-event evidence remains a human research responsibility. Perceptual and geometric screening can flag candidate overlaps but cannot prove that every wildlife event is independent. The platform keeps this qualification visible. Authentication and live-camera ingestion are outside the configured local deployment.

## Executed checks and reproduction

See `artifacts/platform/implementation/VERIFICATION.md` for the executed results and preserved baseline/review checksums.

```powershell
python -m pytest backend/tests/test_review.py backend/tests/test_platform.py backend/tests/test_api.py -q --basetemp artifacts/platform/test_runs/verification
```

The optional real training smoke uses isolated data, registry, model selection, and output storage. It copies existing approved annotations into software fixtures and makes no independent benchmark claim:

```powershell
$env:NAZAR_RUN_TRAIN_SMOKE = '1'
python -m pytest backend/tests/test_platform.py::test_authorized_small_training_evaluation_inference_lifecycle -q --basetemp artifacts/platform/test_runs/smoke
```

Do not infer model improvement from the smoke test's tiny fixture metrics.
