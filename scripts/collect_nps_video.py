"""Download an explicitly public-domain NPS Kemp's ridley project video."""

import hashlib
import json
from datetime import date
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external_test"
PAGE = "https://www.nps.gov/media/video/view.htm?id=E48D8A2F-1F0E-44CD-BC36-29D597C68997"
URL = "https://www.nps.gov/nps-audiovideo/audiovideo/0736888e-d88c-4eaf-88dd-ad9779fd9492480p.mp4"


def main():
    dest = OUT / "originals" / "videos" / "nps_kemps_ridley_project_2016_480p.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        r = requests.get(URL, timeout=90, headers={"User-Agent": "NazarVisionAcademicResearch/0.1"})
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("video/"):
            raise ValueError("NPS returned non-video content")
        dest.write_bytes(r.content)
    cap = cv2.VideoCapture(str(dest))
    if not cap.isOpened():
        raise ValueError("NPS video did not open")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok, _ = cap.read()
    cap.release()
    if not ok:
        raise ValueError("NPS video did not decode")
    row = {"title": "Kemp's ridley Project (NPS, 2016)", "role": "positive", "kind": "video",
           "source_page": PAGE, "direct_url": URL, "license": "Public Domain (NPS credit and usage statement)",
           "license_url": PAGE, "creator": "Padre Island National Seashore Division of Sea Turtle Science and Recovery",
           "credit": "NPS / Padre Island National Seashore", "description": "Edited 49-second promotional clip on Kemp's ridley project; mixed scenes, not continuous beach surveillance",
           "date_original": "2016", "search_query": "NPS Kemp's ridley hatchling video",
           "download_date": date.today().isoformat(), "source_organization": "U.S. National Park Service",
           "group_id": "nps_padre_kemps_ridley_promo_2016",
           "local_path": str(dest.relative_to(ROOT)), "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
           "size_bytes": dest.stat().st_size, "width": width, "height": height, "fps": round(fps, 4),
           "duration_s": round(frames/fps, 3), "frames_reported": frames, "decode_verified": True,
           "license_review": "NPS page credits NPS production and states NPS-credited media without copyright symbol is public domain"}
    manifests = OUT / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "nps_video_manifest.json").write_text(json.dumps([row], indent=2), encoding="utf-8")
    print("OK", row["title"], width, height, fps, frames, dest.stat().st_size)


if __name__ == "__main__":
    main()
