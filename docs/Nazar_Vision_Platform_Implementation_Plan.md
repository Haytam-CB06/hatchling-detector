# Nazar Vision lifecycle platform implementation

The existing React 19 / TypeScript / Vite frontend and FastAPI backend remain the application foundation. `App.tsx` provides actual image/video inference, `ReviewWorkspace.tsx` provides the annotation canvas, and the Task 3 SQLite database remains the review source of record. The baseline checkpoint and original datasets are read-only inputs.

1. Inventory repository resources, prior Task 1–3 evidence, checkpoints, YAML/configuration, review records, and actual compute resources. Save preservation checks in `artifacts/platform/implementation/repository_audit.json`.
2. Add additive SQLite catalog migrations with a database backup and unchanged review-row checks. Add persistent subprocess jobs with logs, cancellation requests, failure recovery, and bounded parameter validation.
3. Index the existing curated dataset and frozen evaluation manifest without copying or approving original labels. Add immutable folder/file/ZIP/video imports and quality findings.
4. Extend the existing annotation canvas to imported images, named reviewers, additional decisions, zoom, shortcuts, and persisted source-event proposals. Preserve legacy approvals and history.
5. Generate versioned YOLO snapshots from approved records only. Require confirmed source events, prevent frozen test contamination, and check exact/perceptual cross-partition overlap. Do not infer event independence from filenames.
6. Run authorized training jobs using local registered checkpoints, bounded settings, explicit resource confirmation, time caps, real CSV metrics, cancellation, and preserved output directories.
7. Register and compare immutable checkpoint hashes; activate a selected detector in the existing inference service. Evaluate only verified snapshots and distinguish validation, independent test, and non-independent test scope.
8. Connect inference uploads to unapproved candidate imports. Preserve actual frame timelines for uploaded video; display the camera integration boundary as unavailable until configured.
9. Export actual persisted records as PDF, CSV, and JSON. Verify imports, review persistence, preparation gates, training/evaluation job mechanics, model selection, inference, reports, and browser navigation using isolated test storage.

Scientific readiness is a data state, not a UI completion claim. The platform must show unresolved source grouping and missing approvals instead of manufacturing a ready dataset. Real smoke experiments, if run, are isolated software checks and are never used to claim independent accuracy or replace the baseline model.
