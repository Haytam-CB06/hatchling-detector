# Nazar Vision - Assumptions and Open Decisions

| Document control | Value |
| --- | --- |
| Version | 0.1 |
| Date | 18 October 2026 |
| Status | Open decision register; no decision below is silently treated as implemented |
| Source | [Project brief](reference/Nazar_Vision_Project_Brief.pdf) |

## Reading this register

The brief is the source for **specified** requirements. Items marked **proposed** are reasonable engineering choices for planning and need validation against the existing repository, available resources, or stakeholder preferences. `TBD` means the supplied brief does not settle the point. Decisions should be recorded with date, owner, rationale, and any effect on the [SRS](Nazar_Vision_Software_Requirements_Specification.md) and [traceability matrix](Nazar_Vision_Requirements_Traceability.md).

## Confirmed planning assumptions

| ID | Assumption and evidence | Consequence |
| --- | --- | --- |
| A-01 | An existing Nazar Vision Python repository will be supplied, but none is present in this workspace. The brief says the first activity is to audit it. (Brief, p. 4.) | This package specifies a target; actual implementation status is **unaudited**. Avoid duplicating existing modules. |
| A-02 | The core project must work with the named public dataset; local conservation footage is not guaranteed. (pp. 5-7, 29.) | Do not make private footage or a physical camera a prerequisite. |
| A-03 | The technical user is a dataset reviewer/model operator using FiftyOne and Python. A custom web dashboard or accounts are not specified. (pp. 7-16.) | User journeys center on FiftyOne plus project commands/runbooks. |
| A-04 | Hatchling detection is mandatory; adult turtles, alerts, tracking, and field use are optional. (pp. 3-4, 17-25, 29.) | Keep optional entities and workflows out of the core acceptance gate. |
| A-05 | No fixed model accuracy percentage is specified. Public-dataset success does not prove nighttime field readiness. (p. 27.) | Define credible evaluation and limitations, not an invented pass percentage. |

## Decisions required

| ID | Decision / question | Current position and next evidence | Owner to confirm | Impact |
| --- | --- | --- | --- | --- |
| D-01 | Which existing modules already satisfy FR-01 to FR-09? | **TBD.** Audit the supplied repository, run its tests, and update actual status. (p. 4.) | Student team + mentor | Work breakdown and ownership |
| D-02 | What are the supported OS, Python, uv, FiftyOne, MongoDB, Ultralytics and PyTorch versions? | **TBD.** Use existing lockfile/docs and a clean setup trial. (pp. 4-5, 16.) | Student team | Reproducible setup |
| D-03 | What compute is available and which initial model is feasible? | Brief expects a small pretrained model, currently YOLO26s; GPU availability is unconfirmed. Verify model availability and benchmark within resources. (pp. 5, 13, 30.) | Student team + supervisor | Training time and experiment plan |
| D-04 | Where will the public dataset be obtained and stored? | **TBD.** Confirm version 24, 694-image claim, license, labels, augmentations, and original splits against downloaded files. (pp. 5-6.) | Dataset steward | Provenance and repeatability |
| D-05 | How will duplicates and source-related groups be identified across splits? | **Proposed:** exact hashes, perceptual similarity, available Roboflow/source metadata, and manual review; document limits. The brief requires leakage investigation but gives no fixed algorithm. (pp. 6, 12, 25-26.) | Dataset steward | Trustworthiness of evaluation |
| D-06 | How will checkpoints be made, retained, and restored? | **TBD:** choose MongoDB backup or FiftyOne dataset export/checkpoint method after environment audit. Define cadence, retention, path mapping, restore test. Pre-export and manual checkpoint behavior are required. (pp. 12-13, 26.) | Maintainer | Recoverability |
| D-07 | What format and location will freeze each experiment's dataset/config state? | **Proposed:** immutable run manifest plus checkpoint ID and export snapshot. The brief requires reproducibility but not a schema. (pp. 13-14, 26.) | ML engineer | Fair run comparison |
| D-08 | Which score threshold, IoU definition, mAP variants, and evaluation slices will be reported? | **TBD.** Choose and record before comparing experiments; include precision, recall, mAP, false positives and false negatives. (pp. 14, 25-27.) | ML engineer + supervisor | Metric comparability |
| D-09 | Is genuine prerecorded hatchling video available? | **TBD.** If unavailable, use an image sequence for frame-by-frame core demonstration and state the limitation. (p. 15.) | Student team + mentor | Demonstration artifact |
| D-10 | Which optional extensions should be selected for a second term? | **TBD.** Gate selection on core completion, dataset availability, time, and resources. (pp. 17, 27-28.) | Supervisor + mentor + students | Scope and schedule |
| D-11 | When and under what license can code or data be published? | **TBD.** Check source/dependency licenses, student contribution rights, and the brief's proposed prohibited uses with appropriate advisers. No public release is required now. (pp. 29, 31.) | Project owner + university | Distribution rights |
| D-12 | What are final university deadlines and submission format? | **TBD.** The brief's timeline is provisional; confirm one or two terms and academic format. (pp. 27-30.) | University supervisor | Delivery schedule |

## Change control

When a decision is resolved, add its result and date in this register, revise affected requirements or test expectations, and link the code or experiment evidence. Changes that move an optional extension into the committed delivery scope should explicitly update the SRS, feature catalog, workflows, and acceptance plan together.
