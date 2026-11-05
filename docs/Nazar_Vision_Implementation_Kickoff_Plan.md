# Nazar Vision — Implementation Kickoff Plan

**Status:** from-scratch implementation plan, 21 October 2026. Git and initial pipeline scripts are initialized. The setup now specifies a Conda environment. The dataset and trained model are not in this workspace.

## 1. The first action

The [project brief](reference/Nazar_Vision_Project_Brief.pdf) (p. 4) assumes an existing Nazar Vision repository. The user has explicitly chosen a **new implementation from scratch** and now specifies **Conda** for Python environment management. This folder is a Git repository with an `environment.yml` and initial data pipeline scripts. Create or activate the intended Conda environment, install its packages, and verify FiftyOne launches before importing the real dataset.

**Why this sequence:** It gives every following import, review, training, and evaluation step a reproducible base. Keep the implementation small and demonstrate one working behavior before adding the next.

## 2. First coding milestone after setup

Build the smallest useful vertical slice: **import a small representative subset of the approved YOLO-format dataset into a persistent FiftyOne dataset and review one annotation**.

1. Verify the dataset identity, version, license, classes, original partitions, and image paths against the downloaded files. Keep the originals unchanged.
2. Import a small set that includes a correct hatchling box, a box needing correction, a background/negative example, and samples from each available split.
3. Store imported boxes in `ground_truth_source` and copy them into editable `ground_truth_reviewed`.
4. Confirm exactly one of `train`, `val`, `test`, or `excluded` is assigned to each imported sample.
5. Change one box only in `ground_truth_reviewed`, close the FiftyOne session, reopen it, and verify the correction and tags persist while `ground_truth_source` is unchanged.

**Definition of done:** A second developer can run the documented import command, open the persistent dataset, identify the source and reviewed fields, repeat one correction, reopen the dataset, and see the saved result. Preserve a short screen recording or verified screenshots and a test log as evidence.

## 3. Next build order

| Order | Capability | Proof to keep |
| --- | --- | --- |
| 1 | Establish the new repository and clean environment | Git initialized; isolated Python interpreter; baseline commands recorded |
| 2 | Persistent import and reviewed annotation workflow | Reopen test; unchanged source field/files; sample tags |
| 3 | Canonical label mapping and pre-export validation | Known bad box, class, or split blocks export with affected sample ID |
| 4 | Checkpoint, restore, and current YOLO export | Restore test; excluded images absent; export tied to dataset state |
| 5 | Baseline YOLO training and validation evaluation | Reloadable weights, recorded settings, metrics, prediction field |
| 6 | Held-out test and prerecorded-video demonstration | Final results, error examples, annotated output, limitations |

This order follows the [usage workflows](Nazar_Vision_User_Usage_Workflows.md) and [architecture setup](Nazar_Vision_Architecture_and_Project_Setup.md). Keep tracking, alerts, live camera input, and a separate dashboard as optional scope until the core is working and those features are explicitly selected.

## 4. Business-owner presentation checkpoint

Use the [system usage presentation](../presentations/Nazar_Vision_System_Usage_and_Workflow_Presentation.pptx) to walk through four examples: review an image, correct a box, block an invalid export, and inspect recorded-video detections. Tell the owner that its screens are **concept mockups** and ask them to confirm:

- Who will operate the first version: a researcher using FiftyOne and Python, or another user group?
- Is the specified local FiftyOne workflow the intended first release, or is a separate browser/mobile interface a new requirement?
- What sample footage or image sequence is available for the final demonstration?
- Which optional capability, if any, matters most **after** the core proof of concept works?

Record answers in [Assumptions and Open Decisions](Nazar_Vision_Assumptions_and_Open_Decisions.md) and revise scope before implementing an interface the owner did not request.
