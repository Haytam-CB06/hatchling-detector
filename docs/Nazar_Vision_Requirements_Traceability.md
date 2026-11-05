# Nazar Vision — Requirements Traceability and Verification Matrix

| Document control | Value |
|---|---|
| Document ID | NV-RTM-001 |
| Version | 1.0, planning baseline |
| Prepared | 18 October 2026 |
| Requirements baseline | [Software Requirements Specification](Nazar_Vision_Software_Requirements_Specification.md), version 1.0 |
| Source baseline | [Nazar Vision Project Brief](reference/Nazar_Vision_Project_Brief.pdf), dated 13 October 2026 |
| Implementation status | **Unaudited.** A trace link is a planned requirement and verification approach, not a claim that code or evidence exists. |

## 1. How to use this matrix

The source's `FR-01`–`FR-09` and `EXT-01`–`EXT-10` identifiers are retained. `AC-xx.y` identifies one acceptance check in the SRS; `NFR-xx` identifies a quality requirement. Each planned check has a primary source page and a verification method/evidence identifier. The verification records in Section 2 are planned artifacts; the team should add links to actual run IDs, screenshots, reports, test output, or commits after execution. Source PDF page numbers are the printed PDF page positions, beginning with the cover as page 1.

**Status values for future updates:** `Not started`, `In progress`, `Verified`, `Failed`, `Deferred`, or `Not applicable`. All items here start as `Not started` until the existing repository is audited. Optional extensions stay `Deferred` unless formally selected. Do not mark a requirement `Verified` because a script exists; execute the check against the agreed dataset and environment. [Source: pp. 4, 8, 17](reference/Nazar_Vision_Project_Brief.pdf#page=4).

## 2. Planned verification records

| Evidence ID | Verification method | Record to retain |
|---|---|---|
| V-01 | Import/integration demonstration against stated Roboflow data | Dataset identity/version, import log, counts, sampled image/box/label/split comparison, FiftyOne view |
| V-02 | Source and field integrity comparison | Before/after source-file checks, `ground_truth_source` vs reviewed comparison, no mutation report |
| V-03 | FiftyOne reviewer walkthrough | Screenshots or concise operator log for edit/add/delete/reclassify, tag change, exclusion, and field schema |
| V-04 | Persist/reopen test | Dataset identifier plus annotation/tag values before and after restart |
| V-05 | Canonical-mapping tests | Configuration, positive/ignored/unknown-label/background fixture results, repeated regeneration result |
| V-06 | Validation failure/success tests | Unassigned, conflicting, excluded, unknown-class, invalid-box fixtures and diagnostics |
| V-07 | Export/integration test | Export manifest and class file, split sample counts/IDs, Ultralytics data-load success, exclusion check |
| V-08 | Data-quality/leakage review | Duplicate/near-duplicate and source-group investigation log, changed tags, unresolved limitations |
| V-09 | Backup and restore drill | Timestamped checkpoint, manual/pre-export creation logs, restored labels/tags/metadata and image path checks |
| V-10 | Training smoke/full run | Training configuration, run ID, saved weights, load/infer proof, training outputs |
| V-11 | Experiment provenance review | Dataset checkpoint/export reference, mapping/splits, model/version/settings, weights and results in a run manifest |
| V-12 | Quantitative evaluation | Precision, recall, mAP definition/value, false-positive/false-negative evidence, partition and model identity |
| V-13 | FiftyOne prediction/error review | Run-specific prediction field, comparison to canonical truth, representative TP/FN/FP/mislocalization examples |
| V-14 | Inference demonstration | Saved model, input provenance, annotated image/video or image sequence, visible boxes/classes/confidence |
| V-15 | Developer quality gate | `pytest`, Ruff, Black, mypy output and reviewed documentation/known-limitation list |
| V-16 | Reproduction walkthrough | Independent operator follows installation through export/training/evaluation/inference and records deviations |
| V-17 | Provenance/licence review | Dataset and software attribution/licence inventory before sharing any artifacts |

## 3. Core functional acceptance trace

Evidence IDs identify what to produce, not files already present. “Design detail” points to a testability choice beyond the exact source wording; Section 6 lists those choices for stakeholder review.

### FR-01 — Dataset import

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-01.1 Import initial YOLO-format source and report counts/failures | [p. 8, FR-01](reference/Nazar_Vision_Project_Brief.pdf#page=8); [pp. 5–6, dataset](reference/Nazar_Vision_Project_Brief.pdf#page=5) | V-01 |
| AC-01.2 Show images, boxes, labels, and original splits in FiftyOne | [p. 8, FR-01](reference/Nazar_Vision_Project_Brief.pdf#page=8) | V-01 |
| AC-01.3 Preserve source field and create separate reviewed copy | [pp. 7–9, workflow/FR-02](reference/Nazar_Vision_Project_Brief.pdf#page=9) | V-01, V-02 |
| AC-01.4 Demonstrate that original files did not change | [p. 8, FR-01](reference/Nazar_Vision_Project_Brief.pdf#page=8) | V-02; design detail D-02 |
| AC-01.5 Define safe rerun/reimport behavior | [p. 8, preserve source/workflow](reference/Nazar_Vision_Project_Brief.pdf#page=8) | V-01; design detail D-03 |

### FR-02 — Dataset review and editing

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-02.1 Configure reviewed editability, source read-only | [pp. 8–9, FR-02](reference/Nazar_Vision_Project_Brief.pdf#page=8) | V-03 |
| AC-02.2 Correct/add/remove boxes and correct class in reviewed field only | [pp. 9–10, FR-02](reference/Nazar_Vision_Project_Brief.pdf#page=9) | V-03, V-02 |
| AC-02.3 Change train/val/test tags and use latest on export | [pp. 9–10, FR-02](reference/Nazar_Vision_Project_Brief.pdf#page=9) | V-03, V-07 |
| AC-02.4 Mark excluded without deleting image or source files | [pp. 6, 9–10, FR-02](reference/Nazar_Vision_Project_Brief.pdf#page=9) | V-03, V-07, V-02 |
| AC-02.5 Interleave corrections, tags, and data-quality review | [pp. 7, 9–10, workflow/FR-02](reference/Nazar_Vision_Project_Brief.pdf#page=9) | V-03, V-08 |
| AC-02.6 Verify corrected annotation/tag after reopen | [pp. 9–10, 12–13, FR-02/FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=12) | V-04 |

### FR-03 — Canonical training labels

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-03.1 Load mapping and field names from configuration | [pp. 10–11, FR-03](reference/Nazar_Vision_Project_Brief.pdf#page=10) | V-05 |
| AC-03.2 Derive canonical field without mutating source/reviewed | [pp. 10–11, FR-03](reference/Nazar_Vision_Project_Brief.pdf#page=11) | V-05, V-02 |
| AC-03.3 Map `sea turtle` to `hatchling`, omit `non-sea-turtle` box but retain image | [pp. 6, 10–11, FR-03](reference/Nazar_Vision_Project_Brief.pdf#page=10) | V-05 |
| AC-03.4 Retain valid zero-positive background examples | [pp. 6, 11, FR-03](reference/Nazar_Vision_Project_Brief.pdf#page=11) | V-05, V-07 |
| AC-03.5 Support explicit refresh and mandatory pre-export refresh | [p. 11, FR-03](reference/Nazar_Vision_Project_Brief.pdf#page=11) | V-05, V-07 |
| AC-03.6 Unknown reviewed label reports error and blocks export | [p. 11, FR-03](reference/Nazar_Vision_Project_Brief.pdf#page=11) | V-05, V-06 |
| AC-03.7 Mapping mechanism allows an added class if extension selected | [pp. 11, 18–19, FR-03/EXT-02](reference/Nazar_Vision_Project_Brief.pdf#page=19) | V-05; class-specific training remains optional |

### FR-04 — Dataset validation and export

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-04.1 Reject an unassigned sample | [p. 12, FR-04](reference/Nazar_Vision_Project_Brief.pdf#page=12) | V-06 |
| AC-04.2 Reject conflicting assignment tags | [pp. 9, 12, FR-02/FR-04](reference/Nazar_Vision_Project_Brief.pdf#page=12) | V-06 |
| AC-04.3 Reject unexpected class or invalid box with diagnostic | [pp. 11–12, FR-03/FR-04](reference/Nazar_Vision_Project_Brief.pdf#page=12) | V-06; box policy D-01 |
| AC-04.4 Export only current train/val/test, never excluded | [pp. 12–14, FR-04/FR-06](reference/Nazar_Vision_Project_Brief.pdf#page=12) | V-07 |
| AC-04.5 Export freshly regenerated canonical labels in YOLO format | [pp. 11–14, FR-03/FR-06](reference/Nazar_Vision_Project_Brief.pdf#page=11) | V-05, V-07 |
| AC-04.6 Inspect related/duplicate cross-split imagery and document disposition | [pp. 6, 12, 25–26, FR-04/evaluation](reference/Nazar_Vision_Project_Brief.pdf#page=25) | V-08; method D-04 |
| AC-04.7 Check required partitions are nonempty for requested operation | [pp. 12–15, valid export/training/evaluation](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-06; design detail D-05 |

### FR-05 — Persistence, backup, and recovery

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-05.1 Make FiftyOne dataset persistent and reopen with labels/tags/metadata | [pp. 12–13, FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=12) | V-04, V-09 |
| AC-05.2 Create labeled checkpoint manually | [p. 13, FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-09 |
| AC-05.3 Create checkpoint automatically before export for training or evaluation | [p. 13, FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-09, V-07 |
| AC-05.4 Define periodic checkpoint practice after significant review | [pp. 7, 13, FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-09; cadence D-06 |
| AC-05.5 Restore reviewed labels, tags, canonical labels, metadata | [p. 13, FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-09 |
| AC-05.6 Restore working paths to source images or report failures | [p. 13, FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-09 |
| AC-05.7 Leave original source files unchanged by backup/restore | [pp. 12–13, FR-05](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-02, V-09 |

### FR-06 — Model training

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-06.1 Use validated train/val canonical data, omit excluded | [pp. 13–14, FR-06](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-07, V-10 |
| AC-06.2 Configure and record model/training settings | [pp. 5, 13–14, FR-06](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-10, V-11 |
| AC-06.3 Save/reload weights and training results under run ID | [pp. 13–14, FR-06](reference/Nazar_Vision_Project_Brief.pdf#page=14) | V-10 |
| AC-06.4 Link run to dataset state, mapping, splits, config, results | [pp. 13, 26, FR-06/reproducibility](reference/Nazar_Vision_Project_Brief.pdf#page=26) | V-11; format D-07 |
| AC-06.5 Run inference on an unseen image using reloaded weights | [p. 14, FR-06](reference/Nazar_Vision_Project_Brief.pdf#page=14) | V-10, V-14 |

### FR-07 — Evaluation and error review

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-07.1 Report precision, recall, mAP, false positives/negatives | [pp. 14–15, 25, FR-07/evaluation](reference/Nazar_Vision_Project_Brief.pdf#page=14) | V-12 |
| AC-07.2 Save predictions in run-specific field separate from ground truth | [p. 14, FR-07](reference/Nazar_Vision_Project_Brief.pdf#page=14) | V-13, V-02 |
| AC-07.3 Inspect correct, missed, false, mislocalized detections in FiftyOne | [pp. 14–15, FR-07](reference/Nazar_Vision_Project_Brief.pdf#page=14) | V-13 |
| AC-07.4 Examine hard images/object size/lighting where practical, state limitations | [pp. 14, 25, FR-07/evaluation](reference/Nazar_Vision_Project_Brief.pdf#page=25) | V-12, V-13 |
| AC-07.5 Compare runs consistently and disclose changes in evaluation data | [pp. 14–15, 26, FR-07/reproducibility](reference/Nazar_Vision_Project_Brief.pdf#page=15) | V-11, V-12 |
| AC-07.6 Reserve test for final independent assessment and report leakage limits | [pp. 7, 15, 25–27, workflow/evaluation](reference/Nazar_Vision_Project_Brief.pdf#page=15) | V-08, V-12 |

### FR-08 — Image and prerecorded-video inference

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-08.1 Load saved weights without retraining | [p. 15, FR-08](reference/Nazar_Vision_Project_Brief.pdf#page=15) | V-14 |
| AC-08.2 Process video or ordered images with boxes/classes/confidence | [p. 15, FR-08](reference/Nazar_Vision_Project_Brief.pdf#page=15) | V-14 |
| AC-08.3 Generate reviewable annotated output without changing input | [p. 15, FR-08](reference/Nazar_Vision_Project_Brief.pdf#page=15) | V-14, V-02 |
| AC-08.4 State image-sequence fallback if no genuine video is available | [p. 15, FR-08](reference/Nazar_Vision_Project_Brief.pdf#page=15) | V-14 |
| AC-08.5 Include frame/class/box/confidence/model in any saved structured results | [p. 15, FR-08: where appropriate](reference/Nazar_Vision_Project_Brief.pdf#page=15) | V-14; format D-08 |

### FR-09 — Testing and documentation

| Acceptance check | Trace to source | Planned evidence |
|---|---|---|
| AC-09.1 Test core processing, persistence, and backup/restore | [pp. 15–16, FR-09](reference/Nazar_Vision_Project_Brief.pdf#page=16) | V-15, V-09 |
| AC-09.2 Run Ruff, Black, mypy using documented commands | [pp. 4, 15–16, FR-09](reference/Nazar_Vision_Project_Brief.pdf#page=16) | V-15 |
| AC-09.3 Document the whole workflow and known limitations | [p. 16, FR-09](reference/Nazar_Vision_Project_Brief.pdf#page=16) | V-15 |
| AC-09.4 Reproduce the main workflow in a supported environment | [p. 16, FR-09](reference/Nazar_Vision_Project_Brief.pdf#page=16) | V-16 |
| AC-09.5 Preserve configuration/results for significant experiments | [pp. 16, 26, FR-09/reproducibility](reference/Nazar_Vision_Project_Brief.pdf#page=26) | V-11 |

## 4. Nonfunctional trace

| SRS ID | Source basis | Verification | Scope |
|---|---|---|---|
| NFR-01 Data integrity | [pp. 5, 8–11, 14](reference/Nazar_Vision_Project_Brief.pdf#page=8) | V-02, V-05, V-13 | Core |
| NFR-02 Reproducibility | [pp. 13–16, 26](reference/Nazar_Vision_Project_Brief.pdf#page=26) | V-11, V-16 | Core |
| NFR-03 Recoverability | [pp. 12–13](reference/Nazar_Vision_Project_Brief.pdf#page=13) | V-09 | Core |
| NFR-04 Maintainability | [pp. 2, 4–5, 15–16](reference/Nazar_Vision_Project_Brief.pdf#page=5) | V-15, code review | Core |
| NFR-05 Configurability | [pp. 5, 10–11, 13](reference/Nazar_Vision_Project_Brief.pdf#page=10) | V-05, V-10 | Core |
| NFR-06 Inspectability | [pp. 8–15](reference/Nazar_Vision_Project_Brief.pdf#page=9) | V-03, V-13 | Core |
| NFR-07 Resource fit | [pp. 5, 13, 16, 29–30](reference/Nazar_Vision_Project_Brief.pdf#page=29) | V-10, V-16, environment record | Core; no numeric target given |
| NFR-08 Licensing/provenance | [pp. 5, 7, 29, 31](reference/Nazar_Vision_Project_Brief.pdf#page=31) | V-17 | Core provenance; future public licence undecided |
| NFR-09 Secret/backup handling | Proposed engineering control; no source-specific auth feature | Config/repository review | Design detail, confirm after audit |

## 5. Optional extension trace

These items do not block core acceptance unless the project team formally selects them. Their potential evidence must be specified in an extension plan before work begins. [Source: p. 17](reference/Nazar_Vision_Project_Brief.pdf#page=17).

| Extension | Source | Planned verification if selected | Initial status |
|---|---|---|---|
| EXT-01 Additional datasets | [pp. 17–18](reference/Nazar_Vision_Project_Brief.pdf#page=17) | Licence/quality/leakage record, compatible import, controlled model comparison | Deferred |
| EXT-02 Adult turtle class | [pp. 18–20](reference/Nazar_Vision_Project_Brief.pdf#page=18) | Same reviewed/canonical workflow, two-class model if data sufficient, per-class metrics/confusions | Deferred |
| EXT-03 Small-object improvement | [p. 20](reference/Nazar_Vision_Project_Brief.pdf#page=20) | At least one controlled alternative vs baseline | Deferred |
| EXT-04 Tracking | [pp. 20–21](reference/Nazar_Vision_Project_Brief.pdf#page=20) | Prerecorded clip with IDs and documented ID failures | Deferred |
| EXT-05 Confidence estimation | [pp. 21–22](reference/Nazar_Vision_Project_Brief.pdf#page=21) | Calibration or track-level method vs baseline on independent labels; correlation assumptions | Deferred |
| EXT-06 Alerts | [pp. 22–23](reference/Nazar_Vision_Project_Brief.pdf#page=22) | Configurable rule, alert evidence image/clip, anti-repeat behavior and observed errors | Deferred |
| EXT-07 Export/integration | [p. 23](reference/Nazar_Vision_Project_Brief.pdf#page=23) | Exported model executes in compatible inference software | Deferred |
| EXT-08 Simulated live feed | [pp. 23–24](reference/Nazar_Vision_Project_Brief.pdf#page=23) | Progressive controlled-rate playback and behavior log | Deferred |
| EXT-09 Physical camera | [p. 24](reference/Nazar_Vision_Project_Brief.pdf#page=24) | Camera capability/cost report; feed processed if equipment exists | Deferred |
| EXT-10 Other wildlife | [pp. 24–25](reference/Nazar_Vision_Project_Brief.pdf#page=24) | Import/configure/train/evaluate new task without substantial core changes | Deferred |

## 6. Design-detail register

These choices are **not** quoted as exact mandates from the brief. They make the brief's requirement measurable or operable; confirm them during the existing-code audit and stakeholder review. No invented numerical detection target is introduced.

| ID | Planned choice | Source need being clarified | Decision owner / next step |
|---|---|---|---|
| D-01 | Define valid normalized box bounds and whether clipping is ever permitted | [p. 12: validate bounding boxes](reference/Nazar_Vision_Project_Brief.pdf#page=12) | ML engineer + reviewer; inspect FiftyOne/YOLO format and data |
| D-02 | Use hashes or another repeatable integrity comparison for source files | [p. 8: original source unchanged](reference/Nazar_Vision_Project_Brief.pdf#page=8) | Maintainer; choose low-cost check |
| D-03 | Make reimport safe against accidental duplicate or overwrite of reviewed work | [pp. 8–10: preserve source and editable review](reference/Nazar_Vision_Project_Brief.pdf#page=9) | Maintainer; audit existing import behavior |
| D-04 | Choose manual FiftyOne review, scripted duplicate candidates, or both | [pp. 6, 12, 25–26: investigate leakage](reference/Nazar_Vision_Project_Brief.pdf#page=25) | Dataset reviewer + ML engineer |
| D-05 | Reject empty partitions required for the requested train/evaluation operation | [pp. 12–15: valid export and evaluation](reference/Nazar_Vision_Project_Brief.pdf#page=13) | ML engineer; define operation-specific check |
| D-06 | Set backup cadence, retention, location, and image-path strategy | [p. 13: periodic and pre-export backups with restore](reference/Nazar_Vision_Project_Brief.pdf#page=13) | Maintainer + mentor |
| D-07 | Choose a run-manifest schema/format and optional seed/hardware fields | [pp. 13, 26: reproduce significant experiments](reference/Nazar_Vision_Project_Brief.pdf#page=26) | ML engineer + maintainer |
| D-08 | Choose machine-readable inference output format if saved | [p. 15: save results where appropriate](reference/Nazar_Vision_Project_Brief.pdf#page=15) | ML engineer; inspect consumers/use case |
| D-09 | Keep credentials out of the repository and restrict backup access | General engineering hygiene; not an explicit brief feature | Maintainer; tailor to environment |

## 7. Source coverage and deliverable alignment

| Source section/pages | Requirement coverage | Graduation-project evidence |
|---|---|---|
| Objectives and design principles, [pp. 3–5](reference/Nazar_Vision_Project_Brief.pdf#page=3) | Scope, FR-01–09, NFR-04–07 | Working software and maintainable source |
| Initial data and review, [pp. 5–7](reference/Nazar_Vision_Project_Brief.pdf#page=5) | Data contract, FR-01–05 | Reviewed persistent dataset and leakage record |
| Core FRs, [pp. 8–16](reference/Nazar_Vision_Project_Brief.pdf#page=8) | AC-01.1 through AC-09.5 | Test records V-01–V-16 |
| Extensions, [pp. 17–25](reference/Nazar_Vision_Project_Brief.pdf#page=17) | EXT-01–10 only when selected | Separate extension plan and evidence |
| Evaluation and reproducibility, [pp. 25–27](reference/Nazar_Vision_Project_Brief.pdf#page=25) | FR-04, FR-06–07, NFR-02 | Metric report, error analysis, checkpoints |
| D1 working software; D2 backups; D3 trained detector, [p. 27](reference/Nazar_Vision_Project_Brief.pdf#page=27) | FR-01–06 | Import/export demonstration, restore drill, saved weights |
| D4 evaluation; D5 video demonstration, [p. 27](reference/Nazar_Vision_Project_Brief.pdf#page=27) | FR-07–08 | Metrics, FiftyOne review, annotated output |
| D6 code/tests; D7 documentation; D8 academic submission, [p. 27](reference/Nazar_Vision_Project_Brief.pdf#page=27) | FR-09, NFR-04–08 | Quality checks, runbook, institution-directed report/presentation |
| Constraints and future development, [pp. 29–31](reference/Nazar_Vision_Project_Brief.pdf#page=29) | Scope boundaries, open decisions | Honest limitation statement and release decision log |

## 8. Change-control notes

1. Audit the repository first, then annotate each FR with `Existing`, `Partial`, or `Missing` and link observed code/tests. This does not change the target acceptance checks by itself. [Source: p. 4](reference/Nazar_Vision_Project_Brief.pdf#page=4).
2. Update the SRS and this matrix together if a requirement is added, withdrawn, or interpreted differently. Keep the source page and decision rationale.
3. Record the actual dataset state, model, and evaluation data for each significant experiment; a later FiftyOne edit can otherwise make an old metric impossible to reproduce. [Source: p. 26](reference/Nazar_Vision_Project_Brief.pdf#page=26).
4. Never promote optional tracking/alerts/camera/public release into the core completion checklist without an explicit scope change. [Source: pp. 17, 29–31](reference/Nazar_Vision_Project_Brief.pdf#page=29).
