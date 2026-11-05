# Hatchling detector model workspace: screen recording guide

## What this platform is

This is a dedicated local workbench for preparing data, training the hatchling detector, evaluating checkpoints, and visualizing what the model actually returns. The detector is intended to serve as the brain of Nazar Vision. This repository is the model lab for that component; it is not the full Nazar Vision product or a deployment dashboard.

The recording should make the model lifecycle visible: source data, human-reviewed labels, a prepared dataset version, a training run, the checkpoint, evaluation evidence, and real inference output.

## Suggested opening

> I built this platform to train and understand the hatchling detector. It gives me one place to curate the data, run controlled experiments, inspect checkpoints, evaluate results, and see the model's predictions. The detector is the brain behind Nazar Vision, while this workspace is dedicated to developing that model.

## Section-by-section walkthrough

### 1. Overview

**Purpose:** A snapshot of dataset volume, review progress, approved boxes, prepared versions, the active detector, recorded metrics, compute, and recent jobs.

**Best practice:** Use it to decide what needs attention next. Open the underlying dataset, model, or job before drawing conclusions from a total or metric. Always read the metric scope shown beside the active model.

**Show and say:** Point out which model is active and whether its validation evidence is recorded. Then show the review and prepared-version counts as workflow status, not a measure of model quality.

### 2. Dataset library

**Purpose:** Imports and catalogs source images, folders, archives, and videos, keeping their names, source details, classes, pool, and provenance together.

**Best practice:** Preserve the original media and describe where it came from. Keep training candidates separate from media reserved for frozen evaluation. Don't merge unrelated sources just to make one larger dataset.

**Show and say:** Open one dataset and point out its source and intended pool. Explain that an import makes media available for review; its existing labels are not automatically verified training truth.

### 3. Quality control

**Purpose:** Surfaces problems such as unreadable files, malformed labels, invalid boxes, duplicates, overlaps, and source-grouping concerns before preparation.

**Best practice:** Investigate each finding against the original media. Treat flags as prompts for review, not automatic instructions to delete data. Resolve confirmed label and file errors before building a training version.

**Show and say:** Open one representative finding, compare it with the source, and explain what evidence would justify correcting, excluding, or retaining it.

### 4. Annotation review

**Purpose:** Lets a human inspect images, correct hatchling boxes, review model suggestions, and save explicit positive, negative, uncertain, rejected, or excluded decisions.

**Best practice:** Inspect the whole image and every box. Approve positive only when hatchlings have valid boxes; approve negative only when no hatchling is present. Keep uncertain cases uncertain, and record the reviewer and useful evidence in notes. Model suggestions are not ground truth until a person reviews them.

**Show and say:** Zoom in on one example, correct or inspect a box, and show how the saved decision records the human review.

### 5. Dataset preparation

**Purpose:** Turns selected approved reviews into a versioned YOLO dataset with source groups, train/validation/test partitions, checksums, and integrity findings.

**Best practice:** Group images from the same recording or wildlife event before assigning partitions, so related frames don't leak across train, validation, and test. Keep frozen evaluation sources out of training. Read every readiness and integrity finding; a passing preflight alone does not prove independent test data.

**Show and say:** Choose an existing version and trace a sample back to its source group and partition. Explain that the prepared version is a reproducible snapshot used by a training run.

### 6. Model training

**Purpose:** Starts a bounded experiment from a prepared dataset version and an initialization checkpoint, then records settings, resources, logs, epoch progress, metrics, and checkpoints.

**Best practice:** Check the dataset version, starting checkpoint, device, image size, epochs, batch, learning rate, optimizer, seed, and resource limits before starting. Change settings intentionally and keep each run's configuration. Preserve the baseline checkpoint. Don't describe a stopped, failed, or incomplete job as a finished result.

**Show and say:** Prefer an existing completed run for the recording. Show its configuration and actual epoch history. Start a new job only when you intend to use the compute and wait for the result.

### 7. Model registry

**Purpose:** Lists preserved checkpoints with their training configuration, file size, checksum, recorded metrics, and active status. It supports checkpoint comparison and activation.

**Best practice:** Compare models only when their datasets and evaluation scopes are comparable. Check the model name and checksum before activation. Keep initialization weights distinct from a trained hatchling detector, and retain the previous baseline for a clear comparison.

**Show and say:** Open a trained checkpoint, identify its source run and dataset version, then show how the active model is selected and verified.

### 8. Evaluation

**Purpose:** Scores a selected trained model against a chosen prepared dataset partition and stores summary metrics, plots, and examples of misses and false detections.

**Best practice:** Use validation data while developing. Keep a truly held-out test set out of training and model selection, and evaluate it only for the final assessment. Review precision, recall, mAP, sample size, source independence, and the error gallery together. A metric is meaningful only within its recorded scope.

**Show and say:** Name the model, dataset version, and partition before reading results. Open a false positive or missed target to connect aggregate metrics to visible model behavior.

### 9. Image & video inference

**Purpose:** Runs the active detector on uploaded media and shows actual boxes, confidence scores, and downloadable annotated results.

**Best practice:** Confirm which checkpoint is active and state the confidence and IoU settings. Inspect both the original and result. A low threshold can increase detections and false positives. Zero boxes means the model returned no detections under those settings; it does not prove the target is absent. Video boxes are frame-level detections, not unique animals.

**Show and say:** Run a representative image or short clip, point out one correct result and one limitation, and read the settings visible on screen.

### 10. Active learning

**Purpose:** Sends difficult or uncertain inference examples into a candidate review flow, where people can correct suggestions before any data is prepared for a later experiment.

**Best practice:** Prioritize diverse, informative examples rather than repeatedly selecting near-duplicates. Preserve source and event information. Human-review every candidate before it enters an approved dataset version.

**Show and say:** Trace one uncertain inference back to the review queue and explain that the model proposes where to look; the reviewer decides what is true.

### 11. Video monitoring

**Purpose:** Displays processed recording timelines and frame-level detections, plus the boundary of the current camera integration.

**Best practice:** Describe this as inspection of uploaded recordings. The live-camera integration is not configured, and frame detections do not count unique animals. Keep source video, date, and processing settings available when discussing a timeline.

**Show and say:** Open a processed recording, point to detections over time, and state clearly that the section does not connect to a live camera or track individual turtles.

### 12. Reports & history

**Purpose:** Provides downloadable technical reports and a history of dataset, review, preparation, training, model, evaluation, and inference activity.

**Best practice:** Keep each conclusion traceable to the dataset version, checkpoint checksum, settings, partition, job ID, and date. Use reports to preserve evidence; don't rely on a cropped screenshot without the run context.

**Show and say:** Open one completed job or report and trace its model and data inputs. Close by showing how an experiment can be revisited later.

## Recommended recording order

Follow the workflow from source data to model behavior:

1. Overview: identify the active model and current workflow state.
2. Dataset library and Quality control: show where the data comes from and how issues are found.
3. Annotation review: show the human-in-the-loop step.
4. Dataset preparation: show event grouping and the immutable version.
5. Model training: show a completed run and its settings.
6. Model registry and Evaluation: connect the checkpoint to evidence and errors.
7. Image & video inference and Active learning: show outputs and how difficult cases return for review.
8. Video monitoring and Reports & history: explain operational limits and traceability.

## Before you press record

- Start both the API and web interface, then confirm the model-ready status before opening the sections you plan to show.
- Choose the actual dataset version, completed run, checkpoint, and evaluation partition in advance so the story follows one experiment end to end.
- Use a completed training run when explaining the workflow. A live run can take time and uses local compute; don't start one only to fill the recording.
- Increase browser zoom enough for labels and settings to be readable, and close unrelated windows before capturing the screen.
- Keep the original and annotated inference result visible together so viewers can connect a prediction to the input.

## Accurate claims to keep in the recording

- Use the model and evaluation scope displayed by the platform; screenshot values can differ from a fresh workspace.
- Don't call a small software fixture an accuracy benchmark.
- Don't claim a test set is independent unless its source-event evidence and overlap checks support that claim.
- Don't describe frame-level boxes as unique-animal counts or the monitoring page as a live camera feed.
- Don't present model suggestions as approved labels; show the human review that verifies them.
