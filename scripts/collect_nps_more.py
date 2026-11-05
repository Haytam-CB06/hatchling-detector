"""Add varied NPS hatchling and beach-negative assets from multiple parks."""

import hashlib
import json
import time
from datetime import date
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external_test"
SEARCHES = [
    "https://npgallery.nps.gov/SearchResults?keyword=hatchling&pagesize=60",
    "https://npgallery.nps.gov/SearchResults?keyword=sea+turtle&pagesize=60&page=2",
]
POSITIVE = {
    "5c8b1257", "2cd53e25", "7c698e6b", "4103443d", "e4dfc998", "30323df7",
    "a930eca1", "7710de6b", "23494732", "64662fda", "81fcd383", "006a173e",
    "f6e08ae3", "ce26269f", "6b3b263d",
}
NEGATIVE = {"fd64c51c", "f70ae6c6", "a956ec56", "ce0a0ab1", "9e9e2455", "93ea647e", "78adc3a1"}


def main():
    session = requests.Session()
    session.headers["User-Agent"] = "NazarVisionAcademicResearch/0.1 (noncommercial evaluation)"
    assets = {}
    for url in SEARCHES:
        r = session.get(url, timeout=45)
        r.raise_for_status()
        page, _ = json.JSONDecoder().raw_decode(r.text.split("var search =", 1)[1].lstrip())
        for item in page["Results"]:
            asset = item["Asset"]
            assets[asset["AssetID"]] = asset
    accepted, rejected = [], []
    for asset_id, asset in assets.items():
        role = "positive" if asset_id[:8] in POSITIVE else "negative" if asset_id[:8] in NEGATIVE else None
        if role is None:
            continue
        rights = asset.get("ConstraintsInformation", {})
        if rights.get("Constraint", "").lower() != "public domain" or rights.get("GrantingRights") != "Full":
            rejected.append({"asset_id": asset_id, "title": asset.get("Title"), "reason": "rights not explicitly public-domain/full"})
            continue
        url = f"https://npgallery.nps.gov/GetAsset/{asset_id}/original.jpg"
        page_url = f"https://npgallery.nps.gov/AssetDetail/{asset_id}"
        path = OUT / ("originals" if role == "positive" else "negatives") / "images" / f"nps_more_{asset_id[:8]}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not path.exists():
                response = session.get(url, timeout=90)
                response.raise_for_status()
                if len(response.content) > 12_000_000 or not response.headers.get("content-type", "").startswith("image/"):
                    raise ValueError("not a usable original JPG under 12 MB")
                path.write_bytes(response.content)
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError("decode failed")
            units = asset.get("NPSUnits") or []
            unit = units[0].get("Name", "NPS") if units else "NPS"
            date_text = asset.get("ImageCreateDate", {}).get("Text", "")
            accepted.append({"title": asset.get("Title", ""), "role": role, "kind": "image",
                             "source_page": page_url, "direct_url": url, "license": "Public Domain", "license_url": page_url,
                             "creator": asset.get("PhotoCredit") or unit, "credit": asset.get("PhotoCredit") or unit,
                             "description": asset.get("Description", ""), "date_original": date_text,
                             "search_query": "NPS Gallery hatchling and sea turtle searches",
                             "download_date": date.today().isoformat(), "source_organization": "U.S. National Park Service / " + unit,
                             "group_id": f"nps_{unit}_{date_text[:10]}", "local_path": str(path.relative_to(ROOT)),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size,
                             "width": image.shape[1], "height": image.shape[0], "fps": "", "duration_s": "",
                             "frames_reported": "", "decode_verified": True,
                             "license_review": "NPS asset ConstraintsInformation: Public domain / Full GrantingRights"})
            print("OK", role, asset.get("Title"), flush=True)
        except Exception as exc:
            path.unlink(missing_ok=True)
            rejected.append({"asset_id": asset_id, "title": asset.get("Title"), "reason": str(exc)})
            print("REJECT", asset.get("Title"), exc, flush=True)
        time.sleep(0.5)
    manifests = OUT / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "nps_more_manifest.json").write_text(json.dumps(accepted, indent=2), encoding="utf-8")
    (manifests / "nps_more_rejected.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")
    print("NPS MORE FINAL", len(accepted), "accepted", len(rejected), "rejected", flush=True)


if __name__ == "__main__":
    main()
