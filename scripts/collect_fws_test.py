"""Download three public-domain USFWS hatchling photos with verified source pages."""

import hashlib
import json
from datetime import date
from pathlib import Path

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external_test"
ITEMS = [
    ("fws_loggerhead_wassaw_2021.jpg", "https://www.fws.gov/media/sea-turtle-hatchling",
     "https://www.fws.gov/sites/default/files/2021-12/sea-turtle-hatchling2-wassaw-nwr-monica-harris.JPG",
     "Monica Harris/USFWS", "2021-12-03", "Loggerhead hatchling traveling from nest to sea at Wassaw NWR"),
    ("fws_green_honu_2025.jpg", "https://www.fws.gov/media/honu-hatchlings",
     "https://www.fws.gov/sites/default/files/images/2025-09/baby-sea-turtles.jpg",
     "Sheldon Plentovich/USFWS", "2025-09-03", "Green hatchlings after nest excavation"),
    ("fws_kemps_ridley_beach_2021.jpg", "https://www.fws.gov/media/kemps-ridley-sea-turtle-hatchlings",
     "https://www.fws.gov/sites/default/files/images/2026-04/kempsridley_hatchlings_texas_coast.JPG",
     "Cynthia Rubio/USFWS", "2021-07-22", "Kemp's ridley hatchlings crossing beach toward the sea"),
]


def main():
    out = OUT / "originals" / "images"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    session = requests.Session()
    session.headers["User-Agent"] = "NazarVisionAcademicResearch/0.1 (noncommercial evaluation)"
    for name, page, url, creator, shot, description in ITEMS:
        path = out / name
        if not path.exists():
            response = session.get(url, timeout=60)
            response.raise_for_status()
            path.write_bytes(response.content)
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"Cannot decode {path}")
        records.append({"title": name, "role": "positive", "kind": "image", "source_page": page,
                        "direct_url": url, "license": "Public Domain (per USFWS media page)", "license_url": page,
                        "creator": creator, "credit": creator, "description": description,
                        "date_original": shot, "search_query": "direct USFWS media search",
                        "download_date": date.today().isoformat(), "source_organization": "U.S. Fish and Wildlife Service",
                        "group_id": page, "local_path": str(path.relative_to(ROOT)),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size,
                        "width": image.shape[1], "height": image.shape[0], "fps": "", "duration_s": "",
                        "frames_reported": "", "decode_verified": True,
                        "license_review": "USFWS page explicitly labels Public Domain"})
        print("OK", name, image.shape[1], image.shape[0], flush=True)
    manifests = OUT / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "fws_manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
