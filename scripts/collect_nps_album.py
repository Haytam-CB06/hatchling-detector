"""Curate public-domain original photos from the NPS Padre Island sea-turtle album."""

import hashlib
import json
import time
from datetime import date
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external_test"
ALBUM = "https://npgallery.nps.gov/SearchResults/albumid/00B48C47-155D-451F-67B48D73D43C3928"

# Asset IDs were selected by reviewing the album's titles, descriptions and
# explicit per-asset public-domain rights. These are one correlated NPS album.
POSITIVE = {
    "00b48eaf", "00b90b7c", "00c500a7", "00da4bc9", "00dd56e5", "00dfb6b0",
    "00e1d03c", "00e4a8ae", "00e84a12", "00eedb47", "00f7621e", "00f89e59",
    "00fc7c42", "00fe2bb3", "00fff1ee", "01015c98", "0105779e", "01074ccd",
    "010b7978", "010d53f4",
}
NEGATIVE = {
    "00bb008f", "00bf386c", "00c11fff", "00c23fb5", "00c6159b", "00ca1589",
    "00cd998b", "00d09d84", "00d4f3f3", "00d8442f", "00f31709", "00f5525b",
    "00f9dc05", "00fa8f42", "010fba6c",
}


def main():
    session = requests.Session()
    session.headers["User-Agent"] = "NazarVisionAcademicResearch/0.1 (noncommercial evaluation)"
    response = session.get(ALBUM, timeout=45)
    response.raise_for_status()
    raw = response.text.split("var search =", 1)[1].lstrip()
    album, _ = json.JSONDecoder().raw_decode(raw)
    accepted, rejected = [], []
    for item in album["Results"]:
        asset = item["Asset"]
        asset_id = asset["AssetID"]
        role = "positive" if asset_id[:8] in POSITIVE else "negative" if asset_id[:8] in NEGATIVE else None
        if role is None:
            continue
        rights = asset.get("ConstraintsInformation", {})
        original = asset.get("FileInfo", {}).get("Original", {})
        if rights.get("Constraint", "").lower() != "public domain" or rights.get("GrantingRights") != "Full":
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": "asset lacks full public-domain grant"})
            continue
        if original.get("FileType", "").lower() != "jpg" or original.get("Size", 0) > 12_000_000:
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": "not a usable JPG original under 12 MB"})
            continue
        url = f"https://npgallery.nps.gov/GetAsset/{asset_id}/original.jpg"
        page = f"https://npgallery.nps.gov/AssetDetail/{asset_id}"
        subdir = "originals" if role == "positive" else "negatives"
        path = OUT / subdir / "images" / f"nps_padre_{asset_id[:8]}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if not path.exists():
                media = session.get(url, timeout=90)
                media.raise_for_status()
                path.write_bytes(media.content)
            frame = cv2.imread(str(path))
            if frame is None:
                raise ValueError("image decode failed")
            accepted.append({"title": asset.get("Title", ""), "role": role, "kind": "image",
                             "source_page": page, "direct_url": url, "license": "Public Domain",
                             "license_url": page, "creator": asset.get("PhotoCredit") or "U.S. National Park Service",
                             "credit": asset.get("PhotoCredit") or "U.S. National Park Service",
                             "description": asset.get("Description", ""),
                             "date_original": asset.get("ImageCreateDate", {}).get("Text", ""),
                             "search_query": "NPS Padre Island sea turtle album",
                             "download_date": date.today().isoformat(), "source_organization": "U.S. National Park Service",
                             "group_id": "nps_padre_sea_turtles_album_2010",
                             "local_path": str(path.relative_to(ROOT)),
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                             "size_bytes": path.stat().st_size, "width": frame.shape[1], "height": frame.shape[0],
                             "fps": "", "duration_s": "", "frames_reported": "", "decode_verified": True,
                             "license_review": "NPS per-asset ConstraintsInformation: Public domain / Full GrantingRights"})
            print("OK", role, asset.get("Title"), flush=True)
        except Exception as exc:
            path.unlink(missing_ok=True)
            rejected.append({"title": asset.get("Title"), "asset_id": asset_id, "reason": str(exc)})
            print("REJECT", asset.get("Title"), exc, flush=True)
        time.sleep(0.5)
    manifests = OUT / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "nps_manifest.json").write_text(json.dumps(accepted, indent=2), encoding="utf-8")
    (manifests / "nps_rejected.json").write_text(json.dumps(rejected, indent=2), encoding="utf-8")
    print("NPS FINAL", len(accepted), "accepted", len(rejected), "rejected", flush=True)


if __name__ == "__main__":
    main()
