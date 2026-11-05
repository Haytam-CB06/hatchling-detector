"""Dataset inspection, provenance, and verified-only version preparation."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image

from .config import ROOT
from .platform_db import PlatformDB, digest, now, uid
from .review import Box, ReviewInput, ReviewStore, _yolo_axis

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
APPROVED = {"verified_positive", "verified_negative"}


def feature_hashes(path):
    with Image.open(path) as im:
        gray = im.convert("L")
        small = np.asarray(gray.resize((32, 32)), dtype=np.float32)
        diff = np.asarray(gray.resize((9, 8)))
    dct = cv2.dct(small)[:8, :8]
    values = dct.flatten()
    phash = sum(int(v > np.median(values[1:])) << i for i, v in enumerate(values))
    dhash = sum(int(v) << i for i, v in enumerate((diff[:, 1:] > diff[:, :-1]).flatten()))
    return f"{phash:016x}", f"{dhash:016x}"


def distance(a, b):
    return (int(a, 16) ^ int(b, 16)).bit_count()


def geometric_overlap(left, right):
    """Bounded ORB/RANSAC crop/scene candidate check; this does not identify a recording."""
    def features(path):
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None: return None, None
        scale = min(1, 800/max(image.shape))
        image = cv2.resize(image, None, fx=scale, fy=scale)
        return cv2.ORB_create(nfeatures=500).detectAndCompute(image, None)
    points_a, desc_a = features(left); points_b, desc_b = features(right)
    if desc_a is None or desc_b is None: return 0
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desc_a, desc_b, k=2)
    good = [pair[0] for pair in matches if len(pair)==2 and pair[0].distance < .7*pair[1].distance]
    if len(good)<20: return 0
    _, mask = cv2.findHomography(np.float32([points_a[m.queryIdx].pt for m in good]), np.float32([points_b[m.trainIdx].pt for m in good]), cv2.RANSAC, 4)
    return int(mask.sum()) if mask is not None and mask.mean()>=.5 else 0


def label_path(image):
    parts = list(image.parts)
    if "images" in parts:
        parts[len(parts) - 1 - parts[::-1].index("images")] = "labels"
        return Path(*parts).with_suffix(".txt")
    return image.with_suffix(".txt")


def parse_yolo(path, width, height, classes):
    boxes, issues = [], []
    if not path.is_file():
        return boxes, [{"severity": "medium", "code": "missing_label", "message": "No source label file; human decision required."}]
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (UnicodeError, OSError):
        return boxes, [{"severity": "high", "code": "invalid_label_encoding", "message": "Label file cannot be read as UTF-8."}]
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            fields = line.split()
            if len(fields) != 5:
                raise ValueError("Expected five detection values")
            cls = int(fields[0])
            x, y, w, h = map(float, fields[1:])
            if cls not in classes:
                raise ValueError(f"Unknown class ID {cls}")
            if not all(math.isfinite(v) for v in (x, y, w, h)) or not (0 < w <= 1 and 0 < h <= 1):
                raise ValueError("Invalid normalized size")
            if not (-1e-6 <= x - w / 2 < x + w / 2 <= 1 + 1e-6 and -1e-6 <= y - h / 2 < y + h / 2 <= 1 + 1e-6):
                raise ValueError("Box extends outside image")
            if min(x-w/2,y-h/2)<-1e-9 or max(x+w/2,y+h/2)>1+1e-9:
                issues.append({'severity':'low','code':'boundary_rounding','message':f'Line {number}: edge reconstruction is within the 1e-6 serialization tolerance. Original YOLO text is preserved.'})
            boxes.append({"id": f"source-{number}", "class_name": classes[cls],
                          "xyxy": [max(0, (x-w/2)*width), max(0, (y-h/2)*height),
                                   min(width, (x+w/2)*width), min(height, (y+h/2)*height)]})
            if w * h < .0005:
                issues.append({"severity": "low", "code": "small_box", "message": f"Source box {number} occupies less than 0.05% of the image."})
            if w * h > .95:
                issues.append({"severity": "low", "code": "large_box", "message": f"Source box {number} covers almost the whole image."})
        except (ValueError, OverflowError) as exc:
            issues.append({"severity": "high", "code": "invalid_label", "message": f"Line {number}: {exc}"})
    return boxes, issues


def inspect_dataset(db: PlatformDB, dataset_id: str, progress=lambda *x: None, aliases=None):
    dataset = db.one("SELECT * FROM platform_datasets WHERE id=?", (dataset_id,))
    root = Path(dataset["root_path"])
    classes = {int(k): str(v) for k, v in json.loads(dataset["classes_json"]).items()}
    configs = sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml"))
    for path in configs:
        try:
            config = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            if isinstance(config, dict) and "names" in config:
                names = config["names"]
                classes = {int(k): str(v) for k, v in (enumerate(names) if isinstance(names, list) else names.items())}
                break
        except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError):
            continue
    images = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    if not images:
        raise ValueError("No supported images were found in the import")
    if len(images) > 5000:
        raise ValueError("An import is limited to 5,000 images; use smaller versioned imports")
    rows, seen, class_counts = [], {}, {}
    existing_paths={r['path'].replace('\\','/'):r['id'] for r in db.all('SELECT id,path FROM platform_images WHERE dataset_id=?',(dataset_id,))}
    frozen_rows = db.all("SELECT id,sha256,phash,dhash FROM platform_images WHERE pool='evaluation'")
    frozen = {r["sha256"] for r in frozen_rows}
    for index, path in enumerate(images):
        sha = digest(path)
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        image_id = existing_paths.get(relative) or (aliases or {}).get(relative) or f"im_{hashlib.sha256((dataset_id + relative).encode()).hexdigest()[:24]}"
        issues, boxes = [], []
        width = height = 0
        phash = dhash = "0000000000000000"
        try:
            with Image.open(path) as image:
                width, height = image.size
                if width * height > 50_000_000:
                    raise ValueError("Image exceeds 50 megapixels")
                if image.getexif().get(274, 1) != 1:
                    issues.append({"severity": "high", "code": "exif_orientation", "message": "EXIF rotation requires visual coordinate confirmation."})
            with Image.open(path) as checked_image:
                checked_image.verify()
            phash, dhash = feature_hashes(path)
            boxes, found = parse_yolo(label_path(path), width, height, classes)
            issues.extend(found)
        except Exception as exc:
            issues.append({"severity": "critical", "code": "corrupt_image", "message": str(exc)[:300]})
        if sha in seen:
            issues.append({"severity": "high", "code": "exact_duplicate", "other_id": seen[sha], "message": "Exact duplicate in this dataset; keep related content in one source group."})
        seen[sha] = image_id
        if path.name.startswith("nps_padre_00b90b7c"):
            issues.append({"severity": "high", "code": "known_resized_duplicate", "message": "Known resized copy of the baseline test source; not independent evidence."})
        if dataset_id=='legacy-training' and path.name.startswith(('st-32_','st-33_','st-34_','st-35_','st-36_')):
            issues.append({'severity':'high','code':'confirmed_legacy_scene_overlap','message':'Task 1 confirmed related beach-scene content across the old train/validation split. Regroup this wildlife event before a new experiment.'})
        pool = "evaluation" if sha in frozen or dataset["pool"] == "evaluation" else "training"
        if sha in frozen and dataset["pool"] == "training":
            issues.append({"severity": "critical", "code": "frozen_source_overlap", "message": "Image matches frozen evaluation media and cannot enter training."})
        elif dataset["pool"] == "training" and width and any(distance(phash,r['phash'])<=5 and distance(dhash,r['dhash'])<=8 for r in frozen_rows):
            issues.append({"severity":"high","code":"suspected_frozen_overlap","message":"Perceptual match to frozen evaluation media; source evidence must be adjudicated before training."})
        for box in boxes:
            class_counts[box["class_name"]] = class_counts.get(box["class_name"], 0) + 1
        split = next((part for part in path.relative_to(root).parts if part in {"train", "valid", "val", "test"}), "unassigned")
        suggestions_path = root.parent / "prediction_suggestions.json"
        saved_predictions = []
        if suggestions_path.is_file():
            saved_predictions = [{"id": f"prediction-{n}", "prediction_id": f"prediction-{n}", "class_name": b["class_name"], "confidence": b["confidence"], "xyxy": b["box_xyxy"]} for n,b in enumerate(json.loads(suggestions_path.read_text(encoding="utf-8")))]
        rows.append((image_id, dataset_id, path.name, relative, sha, width, height, pool, split,
                     f"unknown:{sha[:16]}", json.dumps(boxes), json.dumps(saved_predictions), json.dumps(issues), phash, dhash,
                     json.dumps({"source_label": str(label_path(path).relative_to(ROOT)) if label_path(path).is_relative_to(ROOT) else "", "source_config": [p.name for p in configs],
                                 "source_label_sha256":digest(label_path(path)) if label_path(path).is_file() else None,"parser_version":2,
                                 "inference_context":json.loads((root.parent/'inference_context.json').read_text(encoding='utf-8')) if (root.parent/'inference_context.json').is_file() else None})))
        progress(index + 1, len(images), "Inspecting images and source labels")
    for i, row in enumerate(rows):
        if row[5] == 0:
            continue
        for previous in rows[:i]:
            if row[4] != previous[4] and distance(row[13], previous[13]) <= 5 and distance(row[14], previous[14]) <= 8:
                issues = json.loads(row[12])
                issues.append({"severity": "medium", "code": "near_duplicate", "other_id": previous[0], "message": "Perceptually similar image; inspect source-event relationship."})
                rows[i] = row[:12] + (json.dumps(issues),) + row[13:]
                break
        progress(i+1,len(rows),"Checking perceptual duplicate candidates")
    with db.connection() as conn:
        for row in rows:
            previous = conn.execute("SELECT * FROM platform_images WHERE id=?", (row[0],)).fetchone()
            if previous:
                current_issues = json.loads(row[12])
                previous_meta=json.loads(previous['metadata_json']);new_meta=json.loads(row[15])
                if previous["sha256"] != row[4]:
                    current_issues.append({"severity": "critical", "code": "source_changed", "message": "Source content differs from its recorded import checksum."})
                old_label_sha=previous_meta.get('source_label_sha256')
                if old_label_sha and old_label_sha!=new_meta['source_label_sha256']:
                    current_issues.append({'severity':'critical','code':'source_label_changed','message':'Source label file changed since import; import a new dataset version instead of replacing provenance.'})
                if previous_meta.get('parser_version',1)<2 and previous['sha256']==row[4] and not old_label_sha:
                    merged={**previous_meta,**new_meta,'previous_candidate_parse':json.loads(previous['original_json'])}
                    conn.execute('UPDATE platform_images SET original_json=?,metadata_json=? WHERE id=?',(row[10],json.dumps(merged),row[0]))
                conn.execute("UPDATE platform_images SET issues_json=? WHERE id=?", (json.dumps(current_issues), row[0]))
            else:
                conn.execute("INSERT INTO platform_images VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
    summary = {"images": len(rows), "unsupported_files": [p.name for p in root.rglob('*') if p.is_file() and p.suffix.lower() not in IMAGE_EXTENSIONS | {'.txt','.yaml','.yml','.json','.csv','.md','.zip','.mp4','.mov','.avi'}], "source_boxes": sum(len(json.loads(r[10])) for r in rows),
               "source_positive_images": sum(bool(json.loads(r[10])) for r in rows),
               "source_empty_label_images": sum(label_path(ROOT / r[3]).is_file() and not label_path(ROOT/r[3]).read_text(encoding='utf-8-sig').strip() for r in rows),
               "class_distribution": class_counts, "issues": sum(len(json.loads(r[12])) for r in rows)}
    db.execute("UPDATE platform_datasets SET classes_json=?,summary_json=?,state='imported' WHERE id=?", (json.dumps(classes), json.dumps(summary), dataset_id))
    db.event("dataset_inspected", dataset_id, summary)
    return summary


def bootstrap_catalog(db: PlatformDB, review: ReviewStore):
    """Index existing files; never treat legacy annotations as new human approvals."""
    legacy = db.one("SELECT * FROM platform_datasets WHERE id='legacy-training'")
    if not legacy or legacy["state"] != "imported":
        root = ROOT / "data/generated/hatchling_yolo_v1"
        if root.is_dir():
            db.execute("INSERT OR IGNORE INTO platform_datasets VALUES(?,?,?,?,?,?,?,?,?,?)", (
                "legacy-training", "Baseline hatchlings", "legacy-v1", "Existing curated YOLO export", "training", now(), "indexing", str(root), '{"0":"hatchling"}', '{}'))
            aliases = {item["source_path"]: item["id"] for item in review.items.values() if item["pool"] == "training"}
            inspect_dataset(db, "legacy-training", aliases=aliases)
    if not db.one("SELECT id FROM platform_datasets WHERE id='frozen-evaluation'"):
        db.execute("INSERT INTO platform_datasets VALUES(?,?,?,?,?,?,?,?,?,?)", (
            "frozen-evaluation", "External frozen evaluation", "legacy-v1", "External evaluation manifest", "evaluation", now(), "imported", str(ROOT / 'data/external_test/originals'), '{"0":"hatchling"}', '{}'))
        for item in list(review.items.values()):
            if item["pool"] != "evaluation":
                continue
            phash, dhash = feature_hashes(item["path"])
            issues = [{"severity": "high", "code": "known_resized_duplicate", "message": "Known resized baseline test photograph; exclude from independent scoring."}] if item["filename"].startswith("nps_padre_00b90b7c") else []
            db.execute("INSERT OR IGNORE INTO platform_images VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                item["id"], "frozen-evaluation", item["filename"], item["source_path"], item["sha256"], item["width"], item["height"], "evaluation", "test", item["source_group"], "[]", json.dumps(item["predictions"]), json.dumps(issues), phash, dhash, json.dumps({"source_page": item["source_page"], "source_title": item["source_title"]})))
        count = db.one("SELECT COUNT(*) n FROM platform_images WHERE dataset_id='frozen-evaluation'")["n"]
        db.execute("UPDATE platform_datasets SET summary_json=? WHERE id='frozen-evaluation'", (json.dumps({"images": count}),))


def list_images(db, dataset_id=None):
    query = """SELECT i.*,r.status,r.reviewer,r.reviewed_at,r.revision,r.boxes_json,
       g.group_id confirmed_group,g.split assigned_split,g.confirmed,g.evidence,g.independent
       FROM platform_images i LEFT JOIN reviews r ON r.image_id=i.id
       LEFT JOIN platform_groups g ON g.image_id=i.id"""
    rows = db.all(query + (" WHERE i.dataset_id=?" if dataset_id else ""), (dataset_id,) if dataset_id else ())
    for row in rows:
        for key in ("original_json", "predictions_json", "issues_json", "metadata_json", "boxes_json"):
            row[key.removesuffix("_json")] = json.loads(row.pop(key) or ("{}" if key == "metadata_json" else "[]"))
        row["status"] = row["status"] or "unreviewed"
        row["image_url"] = f"/api/review/images/{row['id']}/media"
        row.pop("path", None)
    return rows


def preparation_preflight(db, review, image_ids, geometric=False):
    errors, warnings, selected = [], [], []
    all_images = {r["id"]: r for r in db.all("SELECT * FROM platform_images")}
    frozen_hashes = {r['sha256'] for r in all_images.values() if r['pool']=='evaluation'}
    if not image_ids:
        errors.append("Select at least one approved image")
    seen_groups = {}
    for image_id in dict.fromkeys(image_ids):
        image = all_images.get(image_id)
        row = db.one("SELECT * FROM reviews WHERE image_id=?", (image_id,))
        group = db.one("SELECT * FROM platform_groups WHERE image_id=?", (image_id,))
        if not image or not row or row["status"] not in APPROVED:
            errors.append(f"{image_id}: no approved annotation")
            continue
        if not group or not group["confirmed"] or not group["reviewer"].strip() or not group["evidence"].strip():
            errors.append(f"{image['filename']}: confirmed source-event group and evidence are required")
            continue
        split = group["split"]
        if split not in {"train", "val", "test"}:
            errors.append(f"{image['filename']}: assign a partition")
        if image["pool"] == "evaluation" and split != "test":
            errors.append(f"{image['filename']}: frozen evaluation media can only be in test")
        if split in {'train','val'} and image['sha256'] in frozen_hashes:
            errors.append(f"{image['filename']}: source matches frozen evaluation media")
        if group["group_id"] in seen_groups and seen_groups[group["group_id"]] != split:
            errors.append(f"Source event {group['group_id']} spans partitions")
        seen_groups[group["group_id"]] = split
        source = ROOT / image['path']
        if not source.is_file():
            errors.append(f"{image['filename']}: referenced source image is missing")
        elif digest(source) != image["sha256"]:
            errors.append(f"{image['filename']}: source checksum changed")
        try:
            boxes = [Box.model_validate(b) for b in json.loads(row["boxes_json"])]
            review.validate({"width": image["width"], "height": image["height"], "predictions": json.loads(image["predictions_json"])},
                            ReviewInput(status=row["status"], boxes=boxes, revision=row["revision"]))
        except Exception as exc:
            errors.append(f"{image['filename']}: invalid annotation: {exc}")
        issues = json.loads(image["issues_json"])
        if any(i["code"] == "corrupt_image" for i in issues):
            errors.append(f"{image['filename']}: corrupted image")
        if any(i['code']=='source_label_changed' for i in issues):
            errors.append(f"{image['filename']}: original labels changed; import a new version to preserve provenance")
        if any(i['code']=='exif_orientation' for i in issues):
            errors.append(f"{image['filename']}: rotated EXIF media requires an upright import and coordinate review")
        if split == "test" and any(i["code"] == "known_resized_duplicate" for i in issues):
            errors.append(f"{image['filename']}: known duplicate cannot be an independent test example; exclude it")
        if split in {"train","val"} and any(i["code"] == "suspected_frozen_overlap" for i in issues):
            decision = db.one("SELECT * FROM platform_quality_decisions WHERE image_id=? AND code='suspected_frozen_overlap'", (image_id,))
            if not decision or decision["decision"] != "distinct_source_confirmed":
                errors.append(f"{image['filename']}: suspected frozen-source overlap requires a documented quality decision")
        selected.append({**image, "review": row, "group": group, "split": split})
    for index, left in enumerate(selected):
        for right in selected[:index]:
            if left["split"] == right["split"]:
                continue
            if left["sha256"] == right["sha256"]:
                errors.append(f"Exact duplicate across partitions: {left['filename']} / {right['filename']}")
            elif distance(left["phash"], right["phash"]) <= 5 and distance(left["dhash"], right["dhash"]) <= 8:
                errors.append(f"Unresolved perceptual overlap across partitions: {left['filename']} / {right['filename']}")
            elif geometric and distance(left["phash"],right["phash"])<=24 and geometric_overlap(ROOT/left["path"],ROOT/right["path"])>=30:
                errors.append(f"Unresolved geometric crop/scene overlap across partitions: {left['filename']} / {right['filename']}")
    counts = {split: sum(i["split"] == split for i in selected) for split in ("train", "val", "test")}
    if not counts["train"] or not counts["val"]:
        errors.append("Training preparation requires approved train and validation groups")
    for partition in ('train','val'):
        if counts[partition] and not any(any(b['class_name']=='hatchling' for b in json.loads(i['review']['boxes_json'])) for i in selected if i['split']==partition):
            errors.append(f"{partition}: at least one approved hatchling box is required for a detector experiment")
    if not counts["test"]:
        warnings.append("No verified test partition; independent test evaluation will be unavailable")
    baseline_sources = db.all("SELECT sha256,phash,dhash FROM platform_images WHERE dataset_id='legacy-training'")
    def unseen_source(image):
        return not any(image['sha256']==r['sha256'] or (distance(image['phash'],r['phash'])<=5 and distance(image['dhash'],r['dhash'])<=8) for r in baseline_sources)
    independent = bool(counts["test"]) and all(i["group"]["independent"] and i["dataset_id"] != "legacy-training" and unseen_source(i) for i in selected if i["split"] == "test")
    if counts["test"] and not independent:
        warnings.append("Test independence has not been established; this partition will be labeled non-independent")
    return {"ready": not errors, "errors": sorted(set(errors)), "warnings": warnings, "counts": counts,
            "independent_test": independent, "selected": selected}


def prepare_version(db, review, payload, progress=lambda *x: None):
    check = preparation_preflight(db, review, payload["image_ids"], geometric=True)
    if not check["ready"]:
        raise ValueError("; ".join(check["errors"]))
    version_id = uid()
    output_root = ROOT / "data/processed" if db.root == (ROOT / "artifacts/platform").resolve() else db.root / "prepared"
    destination = output_root / f"nazar_{version_id[:12]}"
    destination.mkdir(parents=True, exist_ok=False)
    manifest = []
    for index, image in enumerate(check.pop("selected")):
        split, row, group = image["split"], image["review"], image["group"]
        image_dir, label_dir = destination / "images" / split, destination / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True); label_dir.mkdir(parents=True, exist_ok=True)
        filename = image["id"] + Path(image["filename"]).suffix.lower()
        shutil.copyfile(ROOT / image["path"], image_dir / filename)
        lines = []
        for box in json.loads(row["boxes_json"]):
            if box["class_name"] == "hatchling":
                x1, y1, x2, y2 = box["xyxy"]
                x, w = _yolo_axis(x1, x2, image["width"])
                y, h = _yolo_axis(y1, y2, image["height"])
                lines.append(f"0 {x} {y} {w} {h}")
        label = label_dir / (image["id"] + ".txt")
        label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        manifest.append({"image_id": image["id"], "dataset_id": image["dataset_id"], "source_path": image["path"],
                         "source_sha256": image["sha256"], "image": f"images/{split}/{filename}", "label": f"labels/{split}/{image['id']}.txt",
                         "label_sha256": digest(label), "source_group": group["group_id"], "group_evidence": group["evidence"],
                         "split": split, "pool": image["pool"], "reviewer": row["reviewer"], "annotation_revision": row["revision"],
                         "reviewed_at": row["reviewed_at"], "status": row["status"], "boxes": json.loads(row["boxes_json"]),
                         "width": image["width"], "height": image["height"]})
        progress(index + 1, len(payload["image_ids"]), "Copying verified images and labels")
    config = {"path": destination.as_posix(), "train": "images/train", "val": "images/val", "names": {0: "hatchling"}}
    if check["counts"]["test"]:
        config["test"] = "images/test"
    (destination / "dataset.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (destination / "integrity.json").write_text(json.dumps(check, indent=2), encoding="utf-8")
    db.execute("INSERT INTO platform_versions VALUES(?,?,?,?,?,?,?)", (version_id, payload["name"], now(), "ready", str(destination), json.dumps(manifest), json.dumps(check)))
    db.event("dataset_version_prepared", version_id, check)
    return {"version_id": version_id, **check}
