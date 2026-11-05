"""Merge provenance records and flag duplicates without modifying media."""

import csv
import json
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "external_test"
MANIFESTS = DATA / "manifests"
INPUTS = ("media_manifest.json", "nps_manifest.json", "nps_multi_manifest.json", "nps_more_manifest.json", "nps_hard_manifest.json", "nps_video_manifest.json", "fws_manifest.json")


def dhash(path):
    image = cv2.imread(str(path))
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    pixels = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    value = 0
    for bit in (pixels[:, 1:] > pixels[:, :-1]).flatten():
        value = (value << 1) | int(bit)
    return value


def main():
    rows = []
    for name in INPUTS:
        path = MANIFESTS / name
        if path.exists():
            rows.extend(json.loads(path.read_text(encoding="utf-8")))
    unique = []
    seen_hash = {}
    flagged = []
    for row in rows:
        path = ROOT / row["local_path"]
        if not path.exists() or not row.get("decode_verified"):
            flagged.append({"local_path": row["local_path"], "reason": "file missing or unverified"})
            continue
        if row["sha256"] in seen_hash:
            flagged.append({"local_path": row["local_path"], "reason": "exact duplicate", "related_path": seen_hash[row["sha256"]]})
            continue
        seen_hash[row["sha256"]] = row["local_path"]
        unique.append(row)
    image_hashes = []
    for row in unique:
        if row["kind"] != "image":
            continue
        ph = dhash(ROOT / row["local_path"])
        if ph is None:
            continue
        for old_hash, old_row in image_hashes:
            distance = (ph ^ old_hash).bit_count()
            if distance <= 4:
                flagged.append({"local_path": row["local_path"], "reason": "possible visual near duplicate (dHash <=4)",
                                "related_path": old_row["local_path"], "dhash_distance": distance})
                break
        image_hashes.append((ph, row))
    (MANIFESTS / "combined_manifest.json").write_text(json.dumps(unique, indent=2, ensure_ascii=False), encoding="utf-8")
    (MANIFESTS / "duplicate_review.json").write_text(json.dumps(flagged, indent=2), encoding="utf-8")
    if unique:
        columns = list(dict.fromkeys(key for row in unique for key in row))
        with (MANIFESTS / "combined_manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader(); writer.writerows(unique)
    rejected = []
    for name in ("rejected_candidates.json", "nps_rejected.json", "nps_multi_rejected.json", "nps_more_rejected.json", "nps_hard_rejected.json"):
        path = MANIFESTS / name
        if path.exists():
            rejected.extend(json.loads(path.read_text(encoding="utf-8")))
    rejected.extend([
        {"title": "USFWS directly hosted images", "source_page": "https://www.fws.gov/media/sea-turtle-hatchling",
         "reason": "official file server returned HTTP 403; download control respected"},
        {"title": "NPS Hatchling Turtles educational video", "source_page": "https://www.nps.gov/media/video/view.htm?id=145CCFBD-D1B9-2223-993A32B76840416C",
         "reason": "downloadable video was 98 MB at 480p and largely ranger narration; deprioritized for detector testing"},
        {"title": "DVIDS Sea turtle release", "source_page": "https://www.dvidshub.net/video/300560/sea-turtle-release",
         "reason": "the site's download option requires registration/login; no download-control bypass attempted"},
    ])
    (MANIFESTS / "all_rejected_candidates.json").write_text(json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8")
    counts = Counter((r["role"], r["kind"]) for r in unique)
    source = ["# External test media: provenance and use", "",
              "Every file in `combined_manifest.csv` has an individual source page, direct media URL, creator/credit, license, download date, SHA-256 hash, dimensions, and source group. Local files are unmodified bytes from the documented download URL.",
              "", "## Collection", ""]
    for key, count in sorted(counts.items()):
        source.append(f"- {key[0]} {key[1]}: {count}")
    source += ["", "## Source catalogs", "",
               "- [Wikimedia Commons](https://commons.wikimedia.org/): item-level CC or public-domain licenses; the original creators and licenses are in the manifest. The Commons server rate-limited further downloads, so the collection stops at successfully verified items.",
               "- [NPS Padre Island Sea Turtles album](https://npgallery.nps.gov/SearchResults/albumid/00B48C47-155D-451F-67B48D73D43C3928): each included asset declares Public domain with Full granting rights.",
               "- [NPS sea turtle search](https://npgallery.nps.gov/SearchResults?keyword=sea+turtle&pagesize=60): includes Cape Hatteras and Canaveral National Seashore; each included asset declares Public domain with Full granting rights.",
               "", "## Evaluation cautions", "",
               "These are real wildlife photographs and recordings, but most are close handheld or release-event views. No bounding-box annotations are supplied. Positive/negative role is based on source descriptions and visual review candidates; use the evaluation contact sheets to confirm difficult items. Same-event assets share a group ID and must remain together in any future split. `duplicate_review.json` flags visually similar items for manual review. Images or frames matching the project's existing dataset must be excluded from independent metrics. Do not report precision, recall or mAP on this collection without ground-truth annotation and a leakage audit.",
               "", "When sharing annotated previews, preserve each item's original creator and license attribution. CC BY-SA adaptations may require ShareAlike. Public-domain assets are credited for provenance even when attribution is not legally required."]
    (DATA / "SOURCE.md").write_text("\n".join(source) + "\n", encoding="utf-8")
    print("unique media", len(unique), "counts", dict(counts), "duplicate flags", len(flagged), "rejected candidates", len(rejected))


if __name__ == "__main__":
    main()
