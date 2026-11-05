# Nazar Vision — Software Requirements Specification

| Document control | Value |
|---|---|
| Document ID | NV-SRS-001 |
| Version | 1.0, planning baseline |
| Prepared | 18 October 2026 |
| Project | Nazar Vision: sea turtle hatchling detection and conservation monitoring |
| Primary source | [Nazar Vision Project Brief](reference/Nazar_Vision_Project_Brief.pdf) (31 pages, dated 13 October 2026) |
| Requirement status | **Planned requirements. Current code, data, environment, and integration status have not yet been audited.** |
| Intended audience | Student development team, academic supervisor, external technical mentor, and future maintainers |

## 1. Purpose and interpretation

This SRS defines a testable graduation-project proof of concept for preparing an object-detection dataset, training a sea turtle hatchling detector, evaluating it, and running it on prerecorded imagery. It translates the project brief into implementation and acceptance criteria. The source brief is a stakeholder specification, not evidence that any feature already exists. The existing Nazar Vision repository must be reviewed before implementation status or student contributions are claimed. [Source: pp. 2, 4, 8](reference/Nazar_Vision_Project_Brief.pdf#page=4).

**Priority notation:** `C` means core and required for the proof of concept; `E` means optional extension; `D` means a proposed design detail that makes a source requirement testable and must be confirmed during the initial code review. The words *shall* and *must* in a `C` requirement express the intended completed behavior, not the present state. No target accuracy percentage, minimum frame rate, deployment readiness, or production alert service is asserted. [Source: pp. 17, 27, 29](reference/Nazar_Vision_Project_Brief.pdf#page=27).

## 2. Product scope

### 2.1 Core outcome

A developer/researcher can import the versioned public dataset into a persistent FiftyOne dataset; inspect and correct annotations and split tags; generate canonical labels; validate and export a YOLO dataset; train and evaluate a detector; inspect predictions; and run saved weights against images and prerecorded video or an image sequence. The process can be repeated from documented configuration, backed-up dataset state, and saved experiment artifacts. [Source: pp. 3, 7, 8–16, 29](reference/Nazar_Vision_Project_Brief.pdf#page=3).

### 2.2 Scope boundary

The core workflow uses existing FiftyOne annotation and visualization facilities, Ultralytics training/inference, MongoDB persistence, and project commands/configuration. It does **not** require a new annotation web application, user account system, mobile app, on-beach camera, live stream, tracking, automatic alert, or field deployment. Those capabilities are outside the mandatory proof of concept; selected extensions are specified in Section 9. [Source: pp. 4–5, 15, 17, 29](reference/Nazar_Vision_Project_Brief.pdf#page=15).

### 2.3 Success boundary

Acceptance demonstrates a functioning workflow and credible measured results, including documented errors and limitations. Results on the public dataset cannot establish reliable nighttime performance on a real nesting beach. A May 2027 conservation-organisation demonstration is a target milestone, not a claim of deployability. [Source: pp. 27–29](reference/Nazar_Vision_Project_Brief.pdf#page=27).

## 3. Stakeholders, actors, and environment

| Actor | Core tasks | Access/interface |
|---|---|---|
| Dataset reviewer / curator | Inspect source labels and images; edit `ground_truth_reviewed`; add/remove boxes; correct classes; change `train`, `val`, `test`, or `excluded` tags; investigate duplicates and leakage | FiftyOne App and documented project commands |
| ML engineer / researcher | Configure mapping and experiment; prepare/export dataset; train; evaluate; compare predictions and runs; infer on video | Project CLI/scripts, configuration, FiftyOne, saved artifacts |
| Project maintainer | Install dependencies; operate MongoDB; create, verify, and restore checkpoints; maintain tests and documentation | Development environment, filesystem, MongoDB tools |
| Academic reviewer / mentor | Examine documented results, representative errors, reproducibility evidence, and scope completion | Reports, run manifests, demonstration |
| Conservation collaborator | Give feedback on future suitability and potentially provide data | Demonstration or later collaboration; no core operational role |

One person may perform several roles. Role-based login or authorization is not specified by the brief and should not be invented as a core feature. Student, mentor, university, and conservation-organisation responsibilities are described in the source. [Source: pp. 29–30](reference/Nazar_Vision_Project_Brief.pdf#page=30).

**External components.** Python is the development language. FiftyOne provides dataset review, annotation management, and prediction inspection; its persistent working data is stored in MongoDB. Ultralytics YOLO/PyTorch provides model training and inference. OpenCV may support image/video handling. The anticipated development toolchain includes `uv`, Git/GitHub, `pytest`, Ruff, Black, and mypy. The source identifies a small pretrained YOLO model, currently YOLO26s, as the expected starting point; the final model choice should follow available resources and experiments. [Source: pp. 4–5, 13](reference/Nazar_Vision_Project_Brief.pdf#page=4).

## 4. Data contract and invariants

### 4.1 Initial dataset

The brief identifies the IFPE Roboflow Universe dataset **Sea Turtles Hatchling Detection**, version 24, 694 images, YOLO object-detection format, exported 1 October 2026 under CC BY 4.0. It has original train/validation/test partitions and source classes `sea turtle` and `non-sea-turtle`. These are source-stated facts to check at import, not a guarantee that the local copy is present or identical. The downloaded data includes augmented variants; cross-split related images can invalidate an evaluation. [Source: pp. 5–6](reference/Nazar_Vision_Project_Brief.pdf#page=5).

### 4.2 FiftyOne working dataset

| Field or property | Meaning and rule |
|---|---|
| `filepath` / image asset | Reference to the original source image. The image and original annotation files remain unmodified. |
| `ground_truth_source` | Imported original detection labels; read-only after import. |
| `ground_truth_reviewed` | Editable copy of original labels; reviewer corrections and additions are made here. |
| `ground_truth_canonical` | Derived labels for the configured training classes. It may be temporarily stale during review; it is regenerated on request and immediately before every export. |
| Sample tags | Current split assignment. Each image has exactly one of `train`, `val`, `test`, or `excluded` before export. |
| `predictions_<run_id>` | Model detections from a particular experiment, separate from all ground-truth fields. |

All these properties belong to the same FiftyOne working dataset. The persistent MongoDB record is the authoritative editable state; an export is a derived snapshot. [Source: pp. 8–12, 14](reference/Nazar_Vision_Project_Brief.pdf#page=8).

### 4.3 Canonical class mapping

The initial configuration maps `sea turtle` in **reviewed** labels to `hatchling`, and maps `non-sea-turtle` to `null` (omit that positive box). Omitting a box does not remove its image; an image with zero positive boxes may be a background example if it has a valid train/val/test tag. The `excluded` tag removes the entire image from all training-data exports. Any adult turtle originally labelled `sea turtle` must be reviewed and corrected or excluded before it can safely be mapped to `hatchling`. Unknown reviewed labels fail validation rather than being silently converted or discarded. [Source: pp. 6, 10–11, 18](reference/Nazar_Vision_Project_Brief.pdf#page=10).

### 4.4 Split, integrity, and provenance rules

1. Before export, **exactly one** assignment tag must be present per image. No tag is unassigned; two or more assignment tags conflict. Both conditions block export. `excluded` is mutually exclusive with the other three tags. [Source: pp. 9, 12](reference/Nazar_Vision_Project_Brief.pdf#page=12).
2. Canonical detections must have configured class labels and valid bounding boxes. **Design detail D-01:** for FiftyOne's normalized `[x, y, width, height]` representation, require finite values, positive width/height, and a box wholly within the image; document any explicit clipping policy before applying it. [Source requirement: p. 12](reference/Nazar_Vision_Project_Brief.pdf#page=12).
3. Exact and near duplicates, augmented siblings, and frames from a shared video/camera sequence/nesting event should be examined for cross-split leakage. Resolve identified leakage where possible in FiftyOne and record unresolved limitations. A split label is not evidence of independence by itself. [Source: pp. 6, 12, 25–26](reference/Nazar_Vision_Project_Brief.pdf#page=25).
4. The source images and imported source annotations remain unchanged through review, canonical generation, export, training, and backup/restore. [Source: pp. 5, 7–13](reference/Nazar_Vision_Project_Brief.pdf#page=7).
5. The held-out test split is reserved for final independent assessment. Training/configuration decisions normally use training and validation data. If test membership changes or test results are used to tune the model, the resulting assessment must be described as exploratory rather than untouched final testing. [Source: pp. 7, 15, 26](reference/Nazar_Vision_Project_Brief.pdf#page=15).

## 5. End-to-end operational sequence

1. Audit existing repository and establish a supported environment; obtain the stated dataset and record its identity. [Source: pp. 4, 28](reference/Nazar_Vision_Project_Brief.pdf#page=4).
2. Import assets, original labels, and source split assignments into a persistent FiftyOne dataset; make the reviewed field as a copy. [Source: pp. 7–9](reference/Nazar_Vision_Project_Brief.pdf#page=7).
3. Review boxes/classes, amend tags, investigate quality and leakage, and mark unusable images `excluded`. These activities may occur in any order in FiftyOne. [Source: pp. 7, 9–10](reference/Nazar_Vision_Project_Brief.pdf#page=9).
4. On export request, regenerate canonical labels from the latest reviewed labels, validate labels and assignments, checkpoint that validated dataset state immediately before export, and export only `train`, `val`, and `test`. A failed check aborts export with actionable sample identifiers. [Source: pp. 10–13](reference/Nazar_Vision_Project_Brief.pdf#page=12).
5. Train/fine-tune YOLO with train/validation partitions; retain weights, settings, and dataset-state reference. [Source: pp. 13–14](reference/Nazar_Vision_Project_Brief.pdf#page=13).
6. Evaluate on suitable held-out images; store predictions in a separate run field; inspect correct and failed detections. Correct discovered annotation errors in reviewed labels and regenerate/retrain as needed. [Source: pp. 14–15](reference/Nazar_Vision_Project_Brief.pdf#page=14).
7. Load saved weights and run inference on new images and prerecorded video or an image sequence; save reviewable annotated output. [Source: p. 15](reference/Nazar_Vision_Project_Brief.pdf#page=15).
8. Preserve a significant experiment's dataset checkpoint/export, mapping, model/configuration, results, and source-image availability. [Source: pp. 13, 26](reference/Nazar_Vision_Project_Brief.pdf#page=26).

## 6. Core functional requirements

Each acceptance item is independently verifiable. IDs remain stable for implementation, tests, and the companion traceability document.

### FR-01 — Dataset import (`C`)

**Trigger:** operator selects the source dataset/configuration. **Precondition:** source files are available and readable. **Outcome:** a persistent FiftyOne dataset contains source images, annotations, and original split tags without altering the source. [Source: p. 8](reference/Nazar_Vision_Project_Brief.pdf#page=8).

- **AC-01.1** A documented import command can import the initial YOLO-format Roboflow dataset into FiftyOne; the operation reports imported sample and annotation counts and any unreadable files.
- **AC-01.2** Imported sample images, boxes, labels, and train/val/test tags are visible in FiftyOne and match a manually checked representative sample of source files.
- **AC-01.3** Original annotations are stored in `ground_truth_source`; a separate `ground_truth_reviewed` copy is created without altering the original field.
- **AC-01.4** A before/after hash check or equivalent read-only audit on representative original image and label files finds no source-file changes. **Design detail D-02:** choose the integrity-check method during implementation.
- **AC-01.5** Reimport/reopen behavior is documented so a rerun cannot silently duplicate samples or overwrite reviewed work. **Design detail D-03:** choose safe idempotency/replacement behavior after auditing the existing code.

### FR-02 — Dataset review and editing (`C`)

**Trigger:** reviewer opens the working dataset in FiftyOne. **Outcome:** corrections are persisted in the reviewed field and assignment tags; originals stay available unchanged. [Source: pp. 8–10](reference/Nazar_Vision_Project_Brief.pdf#page=8).

- **AC-02.1** FiftyOne's annotation schema allows box and class editing in `ground_truth_reviewed` and keeps `ground_truth_source` read-only.
- **AC-02.2** A reviewer can correct a box, add a missed hatchling box, remove a false box, and correct a class; the changes appear only in `ground_truth_reviewed`.
- **AC-02.3** A reviewer can change an image among `train`, `val`, and `test` by editing sample tags; the latest assignment is used at the next export.
- **AC-02.4** A reviewer can replace a split tag with `excluded`; the image remains inspectable in FiftyOne and its original files are unchanged.
- **AC-02.5** Corrections, tag changes, and leakage investigation can be interleaved without forcing a fixed review order or a separate custom editor.
- **AC-02.6** After closing and reopening the dataset, a sampled corrected annotation and changed split/exclusion tag still have their new values.

### FR-03 — Canonical training labels (`C`)

**Trigger:** explicit regeneration command or any training-data export. **Outcome:** `ground_truth_canonical` reflects the current reviewed field and configured mapping. [Source: pp. 10–11](reference/Nazar_Vision_Project_Brief.pdf#page=10).

- **AC-03.1** Mapping and label-field names are loaded from a project configuration file; the initial mapping is `sea turtle → hatchling` and `non-sea-turtle → null`.
- **AC-03.2** Regeneration creates/replaces the canonical field from `ground_truth_reviewed`; source and reviewed fields retain identical values before and after generation.
- **AC-03.3** `sea turtle` boxes become `hatchling` boxes; `non-sea-turtle` boxes are omitted; the parent image remains in the working dataset.
- **AC-03.4** Images with no positive canonical boxes remain valid background examples when tagged `train`, `val`, or `test`.
- **AC-03.5** A previously generated canonical field is refreshed automatically on each export; a separate manual refresh is available for inspection.
- **AC-03.6** An unexpected reviewed class is reported with affected sample/box identifiers and blocks export; it is not silently dropped or mapped.
- **AC-03.7** The same mapping mechanism can admit additional classes such as `adult_turtle` if EXT-02 is selected; implementation of that class is not required for core completion.

### FR-04 — Dataset validation and YOLO export (`C`)

**Trigger:** export/preparation request. **Precondition:** persistent working dataset is available. **Outcome:** either a valid reproducible YOLO dataset is produced or the request stops with diagnostics. [Source: pp. 11–12](reference/Nazar_Vision_Project_Brief.pdf#page=12).

- **AC-04.1** Export rejects a sample with zero assignment tags and names the affected sample.
- **AC-04.2** Export rejects a sample with multiple assignment tags, including `excluded` plus a split, and names the conflicting tags.
- **AC-04.3** Export rejects unknown canonical classes and invalid boxes, reporting the sample and annotation involved.
- **AC-04.4** After successful validation, only current `train`, `val`, and `test` samples are exported; no `excluded` image or label is in any exported split.
- **AC-04.5** Exported annotations come only from the newly regenerated canonical field and are in a format accepted by the selected Ultralytics training workflow.
- **AC-04.6** A documented FiftyOne-based procedure allows reviewers to inspect duplicate/near-duplicate candidates and cross-split related images, with corrections or residual limitations recorded. **Design detail D-04:** decide whether candidate generation is manual, scripted, or both.
- **AC-04.7** For a training request, export identifies unusable empty train/validation partitions before invoking training; a final test run identifies an unusable empty test partition. **Design detail D-05:** exact minimum counts beyond nonempty are not prescribed.

### FR-05 — Persistence, checkpoint, and recovery (`C`)

**Trigger:** edit, requested backup, pre-export backup, or restore. **Outcome:** the reviewed working state can survive restart and be recovered with its image references. [Source: pp. 7, 12–13](reference/Nazar_Vision_Project_Brief.pdf#page=12).

- **AC-05.1** The working FiftyOne dataset has `persistent = True`; reviewed annotations, tags, canonical labels, and relevant metadata survive a FiftyOne/MongoDB reopen.
- **AC-05.2** An operator can create a labeled MongoDB backup/checkpoint on request and find its timestamp and dataset identity.
- **AC-05.3** A backup/checkpoint is created automatically before exporting data for training or evaluation; an export does not proceed if its required checkpoint fails.
- **AC-05.4** The runbook defines a practical periodic checkpoint cadence after significant annotation changes, without requiring one backup per edit. **Design detail D-06:** interval, retention, and storage location need agreement.
- **AC-05.5** A documented restore test recovers reviewed boxes/classes, all assignment/exclusion tags, canonical field and relevant metadata from a checkpoint.
- **AC-05.6** The restore procedure verifies that referenced image paths resolve; missing assets are explicitly reported. Images need not be duplicated with every MongoDB checkpoint but must remain available.
- **AC-05.7** The original source images and annotation files remain unchanged through checkpoint and restore.

### FR-06 — YOLO training and artifact retention (`C`)

**Trigger:** engineer starts a configured training run from a validated export. **Outcome:** saved, reloadable weights and a documented experiment. [Source: pp. 13–14](reference/Nazar_Vision_Project_Brief.pdf#page=13).

- **AC-06.1** Training uses the current validated `train` and `val` partitions and canonical classes, never an `excluded` sample.
- **AC-06.2** Model selection and important training settings are configurable; the selected pretrained model and settings are recorded for each run.
- **AC-06.3** A training run saves model weights, Ultralytics output/results, and a stable run identifier; the weights can be reloaded in a separate process.
- **AC-06.4** A run manifest references the dataset checkpoint/export, current split assignment state, class mapping, model/configuration, relevant software versions, and training results. **Design detail D-07:** manifest format and optional seed/hardware fields are chosen during implementation.
- **AC-06.5** Reloaded weights produce detections on a previously unseen image without retraining.

### FR-07 — Model evaluation and error review (`C`)

**Trigger:** engineer evaluates a saved model on an appropriate held-out partition. **Outcome:** quantitative results and separated visual predictions. [Source: pp. 14–15, 25–27](reference/Nazar_Vision_Project_Brief.pdf#page=14).

- **AC-07.1** The evaluation reports precision, recall, mAP, and false-positive/false-negative evidence with the split, model, and evaluation settings identified.
- **AC-07.2** Predictions are imported into a run-specific field (for example, `predictions_run_001`) and do not overwrite source, reviewed, or canonical ground truth.
- **AC-07.3** In FiftyOne, a reviewer can compare predictions with canonical labels and inspect examples of correct detections, missed hatchlings, false detections, and mislocated boxes.
- **AC-07.4** The report includes difficult examples or practical subgroup analysis by hatchling size, lighting, background, or image quality where the dataset permits, and states when the dataset cannot support a conclusion.
- **AC-07.5** Distinct runs can be compared with consistent metric definitions and evaluation data; material changes in test membership or label state are disclosed.
- **AC-07.6** The held-out test set is used for final assessment after development choices; limitations and likely effects of any unresolved leakage are reported.

### FR-08 — Image and prerecorded-video inference (`C`)

**Trigger:** user supplies saved model weights and a new image, prerecorded video, or image sequence. **Outcome:** reviewable detections. [Source: p. 15](reference/Nazar_Vision_Project_Brief.pdf#page=15).

- **AC-08.1** A saved model loads for inference without a training step.
- **AC-08.2** The workflow processes frames in a prerecorded video or an ordered image sequence and displays or exports boxes, `hatchling` labels, and detection confidence scores.
- **AC-08.3** An annotated output can be opened and reviewed by a user; the source input remains unchanged.
- **AC-08.4** If no suitable genuine video is available, the demonstration uses an image sequence and states that limitation clearly.
- **AC-08.5** When machine-readable detections are saved, they identify the input/frame, class, box, confidence, and model/run. **Design detail D-08:** output format is selected after checking the existing code and use case.

### FR-09 — Testing, tooling, and documentation (`C`)

**Trigger:** developer sets up or changes the project. **Outcome:** another developer can run and reproduce the workflow. [Source: pp. 15–16](reference/Nazar_Vision_Project_Brief.pdf#page=16).

- **AC-09.1** Automated `pytest` tests cover import/field creation, canonical conversion, unassigned/conflicting/excluded tags, invalid labels/boxes, export, persistence, and checkpoint/restore behavior with suitable fixtures or controlled integration tests.
- **AC-09.2** Documented commands run Ruff, Black, and mypy; any baseline exceptions are explicit rather than silently skipped.
- **AC-09.3** Documentation covers installation and configuration; importing and reviewing in FiftyOne; editing boxes/classes/tags; exclusion; canonical generation; validation/export; training; evaluation/predictions; image/video inference; backup/restore; and known limitations.
- **AC-09.4** A second developer in the stated supported environment can follow the runbook to produce a prepared dataset, training run, evaluation output, and sample inference output using available data and computing resources.
- **AC-09.5** Significant experiment configuration/results are recorded sufficiently to relate outputs to a recoverable dataset state and saved model.

## 7. Nonfunctional requirements and quality gates

The requirements below state qualities expected of the core implementation. Proposed operational thresholds are deliberately left open until hardware and data are known.

| ID | Priority | Requirement and verification |
|---|---|---|
| NFR-01 Data integrity | C | Source assets and `ground_truth_source` stay unchanged; corrections remain in `ground_truth_reviewed`; predictions occupy separate fields. Verify with representative source-file hash/record comparisons and field-level integration tests. [Source: pp. 5, 8–11, 14](reference/Nazar_Vision_Project_Brief.pdf#page=8). |
| NFR-02 Reproducibility | C | A significant result identifies the dataset state, mapping, splits, model, training/evaluation settings, weights, and measured output. Verify that a second operator can reconstruct the run from its manifest/checkpoint or export. Exact numerical determinism across hardware is not guaranteed. [Source: pp. 13–16, 26](reference/Nazar_Vision_Project_Brief.pdf#page=26). |
| NFR-03 Recoverability | C | Checkpoint and restore procedures preserve reviewed labels/tags/metadata and resolve associated image files. Verify via a destructive-to-disposable-copy restore drill, not by jeopardizing the only working database. [Source: pp. 12–13](reference/Nazar_Vision_Project_Brief.pdf#page=13). |
| NFR-04 Maintainability | C | Use modular, readable Python and existing FiftyOne/Ultralytics APIs; avoid duplicate annotation interfaces or custom training algorithms. Verify by code review and documented Ruff/Black/mypy/pytest commands. [Source: pp. 2, 4–5, 15–16](reference/Nazar_Vision_Project_Brief.pdf#page=5). |
| NFR-05 Configurability | C | Class mapping, label-field names, and training parameters are configuration-driven; an unknown label errors explicitly. Verify by changing test configuration and checking the generated labels/training manifest. [Source: pp. 5, 10–11, 13](reference/Nazar_Vision_Project_Brief.pdf#page=10). |
| NFR-06 Inspectability | C | Dataset, annotations, split tags, canonical labels, and run predictions can be examined in FiftyOne; failure messages identify affected samples. Verify with the core user walkthrough. [Source: pp. 8–15](reference/Nazar_Vision_Project_Brief.pdf#page=9). |
| NFR-07 Portability/resource fit | C | Document a supported environment and resource prerequisites, and keep model size/experiment settings configurable for available compute. Verify setup on the agreed environment; record actual run time/memory as observations, with no invented fixed threshold. [Source: pp. 5, 13, 16, 29–30](reference/Nazar_Vision_Project_Brief.pdf#page=29). |
| NFR-08 Licensing/provenance | C | Record dataset origin, version, stated CC BY 4.0 licence, attribution obligations, model/library licences, and any restrictions on redistributing assets/weights. Verify a provenance checklist before sharing deliverables. The final public software licence is a separate open decision. [Source: pp. 5, 7, 29, 31](reference/Nazar_Vision_Project_Brief.pdf#page=31). |
| NFR-09 Secret and backup handling | D | Keep any database credentials out of version control and protect checkpoint access according to the chosen environment. Verify configuration review. The brief does not define an authentication product feature. |

**Performance measurement:** report dataset counts, metric values, inference conditions, and observed run time/throughput when measured. There is no fixed detection-accuracy percentage in the source. Any numerical launch or alert thresholds require evidence and stakeholder agreement before becoming acceptance criteria. [Source: p. 27](reference/Nazar_Vision_Project_Brief.pdf#page=27).

## 8. Verification strategy and deliverables

| Stage | Evidence to retain | Primary requirements |
|---|---|---|
| Import/review demonstration | Dataset identity and counts; sampled source/reviewed comparison; reopened FiftyOne screenshots or recorded checks | FR-01, FR-02, NFR-01 |
| Preparation checks | Passing/failing validation fixtures; latest canonical mapping; exported split manifests; duplicate/leakage review log | FR-03, FR-04 |
| Recovery drill | Timestamped checkpoint; restore log; sample tag/annotation comparison; image path resolution | FR-05, NFR-03 |
| Training/evaluation | Saved weights; run manifest; precision/recall/mAP; FP/FN examples; separated FiftyOne predictions; limitations | FR-06, FR-07, NFR-02 |
| Video demonstration | Saved weights, input provenance, annotated output with class/box/confidence, stated video or image-sequence limitation | FR-08 |
| Developer handover | Setup and operating instructions; passing automated checks; known issues | FR-09, NFR-04–08 |

These evidence items correspond to the source's core deliverables: working software, persistence/backups, trained detector, evaluation, video demonstration, source/tests, technical documentation, and an academic report/presentation under university rules. The academic submission's exact format is set by the university, not this SRS. [Source: p. 27](reference/Nazar_Vision_Project_Brief.pdf#page=27).

## 9. Optional extensions — excluded from core acceptance

The following are **optional** and require explicit selection, data/resource assessment, their own acceptance plan, and updated schedule. The brief does not expect all of them. [Source: p. 17](reference/Nazar_Vision_Project_Brief.pdf#page=17).

| ID | Optional capability | Minimum evidence if selected | Source |
|---|---|---|---|
| EXT-01 | Additional suitable datasets | Licence/quality/leakage review; retrain; compare to original model on a consistent evaluation basis | [pp. 17–18](reference/Nazar_Vision_Project_Brief.pdf#page=17) |
| EXT-02 | `adult_turtle` class | Review/add adult boxes in same FiftyOne fields; map to a second canonical class; train if enough data; report per-class results and confusions. Adult detection does not imply sex or nesting behavior. | [pp. 18–20](reference/Nazar_Vision_Project_Brief.pdf#page=18) |
| EXT-03 | Small-object improvement | Controlled comparison of at least one alternative against a documented baseline; report effect on adult class if present | [p. 20](reference/Nazar_Vision_Project_Brief.pdf#page=20) |
| EXT-04 | Multi-object tracking | Annotated prerecorded footage with reasonably stable IDs and documented ID switches/failures | [pp. 20–21](reference/Nazar_Vision_Project_Brief.pdf#page=20) |
| EXT-05 | Confidence correctness estimation | Calibrate/check detection confidence against held-out truth, compare baseline; track-level evidence only if suitable labelled video exists; account for frame correlation | [pp. 21–22](reference/Nazar_Vision_Project_Brief.pdf#page=21) |
| EXT-06 | Automatic alerts | Configurable class-aware rule, reviewable image/clip, anti-repeat behavior; measure false/repeated and delayed alerts where practical | [pp. 22–23](reference/Nazar_Vision_Project_Brief.pdf#page=22) |
| EXT-07 | Model export/integration | Demonstrate exported model in compatible inference software and document format/hardware gaps | [p. 23](reference/Nazar_Vision_Project_Brief.pdf#page=23) |
| EXT-08 | Simulated live feed | Progressive playback at a controlled rate, with detections and any selected tracking/alerts | [pp. 23–24](reference/Nazar_Vision_Project_Brief.pdf#page=23) |
| EXT-09 | Physical nighttime camera | Document a configuration's cost/capabilities/limits; process a feed if camera available; field use requires permissions and conservation assessment of illumination | [p. 24](reference/Nazar_Vision_Project_Brief.pdf#page=24) |
| EXT-10 | Other wildlife task | Reconfigure/import/annotate/train/evaluate another dataset without substantial core-code changes | [pp. 24–25](reference/Nazar_Vision_Project_Brief.pdf#page=24) |

Future public release, supervised beach field trials, and site-specific conservation models are longer-term intentions, not compulsory graduation deliverables. The source proposes prohibiting human surveillance, law-enforcement, military, and espionage uses; a suitable licence and compatibility with third-party licences/intellectual-property rights must be resolved before any public release. [Source: p. 31](reference/Nazar_Vision_Project_Brief.pdf#page=31).

## 10. Constraints, assumptions, and open decisions

### 10.1 Confirmed constraints from the brief

- Core completion must be possible with the initial public dataset; local conservation footage and further datasets are not guaranteed. [Source: pp. 7, 29](reference/Nazar_Vision_Project_Brief.pdf#page=29).
- Available GPU/computing capacity is not yet confirmed; experiments must fit actual resources. [Source: pp. 29–30](reference/Nazar_Vision_Project_Brief.pdf#page=30).
- Existing code is under active development; functionality and student ownership require an initial audit. [Source: pp. 4, 30](reference/Nazar_Vision_Project_Brief.pdf#page=4).
- Licensing and attribution for data, code, libraries, and models must be respected. [Source: pp. 7, 29, 31](reference/Nazar_Vision_Project_Brief.pdf#page=31).
- Physical camera acquisition/testing, conservation participation, beach deployment, operational alerts, and reliable night detection are not core prerequisites. [Source: pp. 24, 29–31](reference/Nazar_Vision_Project_Brief.pdf#page=29).

### 10.2 Decision register

| ID | Decision to make during discovery | Impact if deferred |
|---|---|---|
| OD-01 | Record the existing repository's implemented/incomplete functionality, interfaces, and test baseline | Prevents honest implementation planning and attribution of student work |
| OD-02 | Confirm supported OS/Python/FiftyOne/Ultralytics/MongoDB versions and available GPU/storage | Determines reproducible setup and feasible model/training settings |
| OD-03 | Confirm access to the exact dataset version, its licence record, image identities, and any existing video | Determines import checks and video demonstration medium |
| OD-04 | Define duplicate/near-duplicate evidence, source-grouping policy, and how split corrections are logged | Determines credibility of validation/test metrics |
| OD-05 | Select backup tool, frequency/retention/location, asset path strategy, and restore drill environment | Determines recoverability of dataset revisions |
| OD-06 | Select run naming and manifest format, artifact storage, prediction-field lifecycle, and data/export retention | Determines whether results remain traceable after later edits |
| OD-07 | Agree on any optional extensions, their data prerequisites, dates, and acceptance criteria | Prevents optional work from displacing core completion |
| OD-08 | Resolve software/data/model redistribution and the future licence/use restrictions before public release | Avoids incompatible or unapproved release claims |

## 11. Glossary

| Term | Meaning |
|---|---|
| Annotation | A class-labelled bounding box on an image or frame. |
| Canonical label | A reviewed annotation mapped to the configured training-class vocabulary. |
| Background image | A retained image with no positive canonical boxes; it may teach the model non-target appearance. |
| Assignment tag | Exactly one of `train`, `val`, `test`, or `excluded` on a FiftyOne sample. |
| Data leakage | Related or duplicate source content appearing across partitions in a way that biases evaluation. |
| mAP | Mean average precision, an object-detection evaluation metric; its IoU setting/version must be reported. |
| Experiment / run | A particular exported dataset state, model/configuration, training/evaluation outputs, and saved weights. |
| Checkpoint | A recoverable record of the persistent working dataset, coupled with accessible source-image references. |

The companion [Requirements Traceability](Nazar_Vision_Requirements_Traceability.md) records source pages and verification evidence for every requirement family.
