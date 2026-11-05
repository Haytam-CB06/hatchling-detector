"""Collect NPS public-domain crabs, shells, and shorebirds as hard negatives."""

import hashlib
import json
import time
from datetime import date
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external_test"
SEARCH = "https://npgallery.nps.gov/SearchResults"
IDS = {"57e39007", "d1da01ab", "2a2d89fc", "01a8ae4c", "013d149a",
       "01d8d224", "ee22d6fa", "0fbf2e88", "318b6e1b"}


def main():
    session = requests.Session()
    session.headers["User-Agent"] = "NazarVisionAcademicResearch/0.1 (noncommercial evaluation)"
    assets = {}
    for term in ("ghost crab", "seashell", "shorebird"):
        r = session.get(SEARCH, params={"keyword": term, "pagesize": 30}, timeout=45)
        r.raise_for_status()
        page, _ = json.JSONDecoder().raw_decode(r.text.split("var search =", 1)[1].lstrip())
        for item in page["Results"]:
            asset = item["Asset"]
            assets[asset["AssetID"]] = asset
    accepted, rejected = [], []
    for asset_id, asset in assets.items():
        if asset_id[:8] not in IDS:
            continue
        rights = asset.get("ConstraintsInformation", {})
        if rights.get("Constraint", "").lower() != "public domain" or rights.get("GrantingRights") != "Full":
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": "rights not public-domain/full"})
            continue
        url = f"https://npgallery.nps.gov/GetAsset/{asset_id}/original.jpg"
        page_url = f"https://npgallery.nps.gov/AssetDetail/{asset_id}"
        path = OUT / "negatives" / "images" / f"nps_hard_{asset_id[:8]}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not path.exists():
                r = session.get(url, timeout=90)
                r.raise_for_status()
                if len(r.content) > 12_000_000 or not r.headers.get("content-type", "").startswith("image/"):
                    raise ValueError("unusable or oversized original")
                path.write_bytes(r.content)
            frame = cv2.imread(str(path))
            if frame is None:
                raise ValueError("decode failed")
            units = asset.get("NPSUnits") or []
            unit = units[0].get("Name", "NPS") if units else "NPS"
            date_text = asset.get("ImageCreateDate", {}).get("Text", "")
            accepted.append({"title": asset.get("Title", ""), "role": "negative", "kind": "image",
                             "source_page": page_url, "direct_url": url, "license": "Public Domain", "license_url": page_url,
                             "creator": asset.get("PhotoCredit") or unit, "credit": asset.get("PhotoCredit") or unit,
                             "description": asset.get("Description", ""), "date_original": date_text,
                             "search_query": "NPS Gallery ghost crab / seashell / shorebird",
                             "download_date": date.today().isoformat(), "source_organization": "U.S. National Park Service / " + unit,
                             "group_id": f"nps_{unit}_{date_text[:10]}", "local_path": str(path.relative_to(ROOT)),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size,
                             "width": frame.shape[1], "height": frame.shape[0], "fps": "", "duration_s": "",
                             "frames_reported": "", "decode_verified": True,
                             "license_review": "NPS per-asset Public domain / Full GrantingRights"})
            print("OK", asset.get("Title"), flush=True)
        except Exception as exc:
            path.unlink(missing_ok=True)
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": str(exc)})
            print("REJECT", asset.get("Title"), exc, flush=True)
        time.sleep(0.5)
    manifests = OUT / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "nps_hard_manifest.json").write_text(json.dumps(accepted, indent=2), encoding="utf-8")
    (manifests / "nps_hard_rejected.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")
    print("HARD NEG FINAL", len(accepted), "accepted", len(rejected), "rejected")


if __name__ == "__main__":
    main()
