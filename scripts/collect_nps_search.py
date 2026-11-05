"""Collect additional NPS public-domain sea turtle photos from multiple parks."""

import hashlib
import json
import time
from datetime import date
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external_test"
SEARCH = "https://npgallery.nps.gov/SearchResults?keyword=sea+turtle&pagesize=60"
POSITIVE = {
    "f458e71a", "dccf166b", "62fa7d17", "d3c1c49e", "040bca77", "2149bc66",
    "b7048c91", "2fb1ce57", "5b7347b2", "292d2911", "1395b4f4", "4a92e796",
    "62508d50", "603105c9",
}
NEGATIVE = {
    "433342e1", "5d98f6d3", "e84e2b1a", "b044d50b", "c25e77b0", "e45da4a0",
    "fe174d14", "b1c3908c", "4bd55906", "9f9f7411", "557b88b0", "03970d59",
    "96a0ba28", "9c8200d1", "ae606df3",
}


def main():
    session = requests.Session()
    session.headers["User-Agent"] = "NazarVisionAcademicResearch/0.1 (noncommercial evaluation)"
    response = session.get(SEARCH, timeout=45)
    response.raise_for_status()
    raw = response.text.split("var search =", 1)[1].lstrip()
    page, _ = json.JSONDecoder().raw_decode(raw)
    accepted, rejected = [], []
    for item in page["Results"]:
        asset = item["Asset"]
        asset_id = asset["AssetID"]
        role = "positive" if asset_id[:8] in POSITIVE else "negative" if asset_id[:8] in NEGATIVE else None
        if role is None:
            continue
        rights = asset.get("ConstraintsInformation", {})
        original = asset.get("FileInfo", {}).get("Original", {})
        if rights.get("Constraint", "").lower() != "public domain" or rights.get("GrantingRights") != "Full":
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": "rights not explicitly public domain/full"})
            continue
        if original and (original.get("FileType", "").lower() not in ("jpg", "jpeg") or original.get("Size", 0) > 12_000_000):
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": "unsupported or oversized original"})
            continue
        url = f"https://npgallery.nps.gov/GetAsset/{asset_id}/original.jpg"
        source_page = f"https://npgallery.nps.gov/AssetDetail/{asset_id}"
        path = OUT / ("originals" if role == "positive" else "negatives") / "images" / f"nps_multi_{asset_id[:8]}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not path.exists():
                r = session.get(url, timeout=90)
                r.raise_for_status()
                if len(r.content) > 12_000_000 or not r.headers.get("content-type", "").startswith("image/"):
                    raise ValueError("original exceeds 12 MB or is not an image")
                path.write_bytes(r.content)
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError("image decode failed")
            units = asset.get("NPSUnits") or []
            unit = units[0].get("Name", "NPS") if units else "NPS"
            date_text = asset.get("ImageCreateDate", {}).get("Text", "")
            accepted.append({"title": asset.get("Title", ""), "role": role, "kind": "image",
                             "source_page": source_page, "direct_url": url, "license": "Public Domain", "license_url": source_page,
                             "creator": asset.get("PhotoCredit") or unit, "credit": asset.get("PhotoCredit") or unit,
                             "description": asset.get("Description", ""), "date_original": date_text,
                             "search_query": "NPS Gallery sea turtle search", "download_date": date.today().isoformat(),
                             "source_organization": "U.S. National Park Service / " + unit,
                             "group_id": f"nps_{unit}_{date_text[:10]}",
                             "local_path": str(path.relative_to(ROOT)),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size,
                             "width": image.shape[1], "height": image.shape[0], "fps": "", "duration_s": "",
                             "frames_reported": "", "decode_verified": True,
                             "license_review": "NPS per-asset ConstraintsInformation: Public domain / Full GrantingRights"})
            print("OK", role, asset.get("Title"), flush=True)
        except Exception as exc:
            path.unlink(missing_ok=True)
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": str(exc)})
            print("REJECT", asset.get("Title"), exc, flush=True)
        time.sleep(0.5)
    manifests = OUT / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "nps_multi_manifest.json").write_text(json.dumps(accepted, indent=2), encoding="utf-8")
    (manifests / "nps_multi_rejected.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")
    print("NPS MULTI FINAL", len(accepted), "accepted", len(rejected), "rejected", flush=True)


if __name__ == "__main__":
    main()
