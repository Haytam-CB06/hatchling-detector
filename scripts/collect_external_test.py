"""Collect attributed, openly licensed real media for external model testing.

Run from the project root with the nazar-vision Python interpreter. Commons API
metadata is retained verbatim in the JSON manifest; originals are never edited.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote

import cv2
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external_test"
MANIFESTS = OUT / "manifests"
API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "NazarVisionAcademicResearch/0.1 (noncommercial computer-vision evaluation; Wikimedia Commons API)"}
IMAGE_QUERIES = [
    ("sea turtle hatchling", 130),
    ("loggerhead sea turtle hatchling", 70),
    ("green sea turtle hatchling", 70),
    ("olive ridley hatchlings", 50),
    ("leatherback hatchling", 50),
    ("hawksbill hatchling", 50),
    ("Kemp's ridley hatchling", 50),
    ("sea turtle hatchlings beach", 70),
]
NEGATIVE_QUERIES = [
    ("ghost crab beach", 30),
    ("empty beach sand", 30),
    ("seashells sand beach", 30),
    ("shorebird beach sand", 30),
    ("adult sea turtle beach", 30),
    ("seaweed sand beach", 30),
]
POSITIVE_VIDEO_TITLES = [
    "File:Race for survival.webm",
    "File:Loggerhead Sea Turtle Release (7609575862).webm",
    "File:Green Sea Turtle Hatchling In Fishing Line (51178348095).webm",
    "File:Leatherback baby turtle running to sea.webm",
    "File:Unexpected hatchlings (4887337135).webm",
    "File:Kosgoda Sea Turtle Conservation Project video .ogv",
    "File:Baby turtle.webm",
]
NEGATIVE_VIDEO_TITLES = [
    "File:Sea Turtle.ogv",
    "File:Hawksbill Turtle on the GBR.webm",
    "File:Biologists dig turtle eggs (4823815661).webm",
]
ALLOWED_LICENSES = ("public domain", "cc0", "cc by", "cc-by", "cc-by-sa", "cc by-sa")
SKIP_PATTERNS = ("first steps of hatchling of loggerhead", "hatchling of loggerhead sea turtle (caretta caretta) running to sea")


def api(session: requests.Session, **params):
    params.update(action="query", format="json", formatversion=2)
    last_error = "unknown"
    for attempt in range(6):
        try:
            r = session.get(API, params=params, timeout=45)
            if r.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {r.status_code}: {r.text[:160]}"
                time.sleep(min(60, max(10, 10 * (attempt + 1))))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt == 5:
                break
            time.sleep(min(30, 5 * (attempt + 1)))
    raise RuntimeError(f"Commons API unavailable: {last_error}")


def search(session, query, limit):
    found = []
    offset = 0
    while len(found) < limit:
        j = api(session, list="search", srsearch=query, srnamespace=6,
                srlimit=min(50, limit - len(found)), sroffset=offset)
        batch = j.get("query", {}).get("search", [])
        if not batch:
            break
        found.extend(x["title"] for x in batch)
        offset += len(batch)
        if len(batch) < min(50, limit - len(found)):
            break
    return found[:limit]


def metadata(session, titles):
    for pos in range(0, len(titles), 45):
        j = api(session, titles="|".join(titles[pos:pos+45]), prop="imageinfo",
                iiprop="url|size|mime|sha1|extmetadata", iiurlwidth=1280)
        for page in j.get("query", {}).get("pages", []):
            if page.get("imageinfo"):
                yield page
        time.sleep(8)


def clean(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    return " ".join(html.unescape(value).split())


def field(meta, key):
    return clean(meta.get(key, {}).get("value", ""))


def name_for(page):
    title = page["title"].removeprefix("File:")
    ext = Path(title).suffix.lower()
    stem = unicodedata.normalize("NFKD", Path(title).stem).encode("ascii", "ignore").decode()
    stem = re.sub(r"[^a-zA-Z0-9]+", "_", stem).strip("_").lower()[:80]
    return f"{stem}_{page['pageid']}{ext}"


def media_kind(title, info):
    mime = info.get("mime", "")
    ext = Path(title).suffix.lower()
    if mime in ("image/jpeg", "image/png") and ext in (".jpg", ".jpeg", ".png"):
        return "image"
    if mime.startswith("video/") and ext in (".webm", ".ogv", ".mp4"):
        return "video"
    return None


def download(session, url, path, expected_size):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (expected_size is None or path.stat().st_size == expected_size):
        return
    tmp = path.with_suffix(path.suffix + ".part")
    for attempt in range(4):
        try:
            with session.get(url, stream=True, timeout=90) as response:
                response.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)
            if expected_size is not None and tmp.stat().st_size != expected_size:
                raise ValueError(f"size mismatch: {tmp.stat().st_size} vs {expected_size}")
            tmp.replace(path)
            return
        except Exception:
            tmp.unlink(missing_ok=True)
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def checksum(path, algo):
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def decode(path, kind):
    if kind == "image":
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError("image decode failed")
        return {"width": image.shape[1], "height": image.shape[0], "fps": "", "duration_s": "", "frames_reported": ""}
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("video open failed")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok, _ = cap.read()
    cap.release()
    if not ok or width < 1 or height < 1:
        raise ValueError("video first-frame decode failed")
    return {"width": width, "height": height, "fps": round(fps, 4),
            "duration_s": round(frame_count / fps, 3) if fps else "", "frames_reported": int(frame_count)}


def main():
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    candidates = {}
    cached = MANIFESTS / "search_candidates.json"
    if cached.exists():
        candidates = json.loads(cached.read_text(encoding="utf-8"))
        print("using cached search candidates", len(candidates), flush=True)
    else:
      for query, limit in IMAGE_QUERIES:
          print("search positive", query, flush=True)
          try:
              titles = search(session, query, limit)
          except Exception as exc:
              print("search skipped", query, exc, flush=True)
              continue
          for title in titles:
              candidates.setdefault(title, {"role": "positive", "search_query": query})
          time.sleep(2)
      for query, limit in NEGATIVE_QUERIES:
          print("search negative", query, flush=True)
          try:
              titles = search(session, query, limit)
          except Exception as exc:
              print("search skipped", query, exc, flush=True)
              continue
          for title in titles:
              candidates.setdefault(title, {"role": "negative", "search_query": query})
          time.sleep(2)
    for title in POSITIVE_VIDEO_TITLES:
        candidates[title] = {"role": "positive", "search_query": "curated video discovery"}
    for title in NEGATIVE_VIDEO_TITLES:
        candidates[title] = {"role": "negative", "search_query": "curated negative video"}
    (MANIFESTS / "search_candidates.json").write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
    print("candidate titles", len(candidates), flush=True)

    # Query a balanced subset to respect the Commons API rate limit.
    by_query = {}
    for title, attributes in candidates.items():
        by_query.setdefault(attributes["search_query"], []).append(title)
    metadata_titles = []
    for query, titles in by_query.items():
        cap = 12 if query in ("curated video discovery", "curated negative video") else (17 if any(query == q for q, _ in IMAGE_QUERIES) else 9)
        metadata_titles.extend(titles[:cap])
    metadata_titles = list(dict.fromkeys(metadata_titles))
    print("metadata subset", len(metadata_titles), flush=True)

    selected = []
    rejected = []
    counts = Counter()
    series = Counter()
    selected_cache = MANIFESTS / "selected_metadata.json"
    if selected_cache.exists():
        selected = json.loads(selected_cache.read_text(encoding="utf-8"))
        print("using cached selected metadata", len(selected), flush=True)
    else:
      for page in metadata(session, metadata_titles):
        title = page["title"]
        if title not in candidates:
            continue
        role = candidates[title]["role"]
        info = page["imageinfo"][0]
        meta = info.get("extmetadata", {})
        license_name = field(meta, "LicenseShortName")
        license_url = field(meta, "LicenseUrl")
        kind = media_kind(title, info)
        size = info.get("size", 0)
        reason = ""
        lower = title.lower()
        if any(p in lower for p in SKIP_PATTERNS):
            reason = "same shoot as pre-existing reference video; excluded from new collection"
        elif kind is None:
            reason = "unsupported media format"
        elif not license_name or not any(x in license_name.lower() for x in ALLOWED_LICENSES):
            reason = "reuse license absent or not in allowed open-license list"
        elif size > (35_000_000 if kind == "video" else 14_000_000):
            reason = "original exceeds collection size cap"
        elif size < 20_000:
            reason = "file too small for meaningful evaluation"
        elif role == "positive" and kind == "image" and not any(x in lower for x in ("sea turtle", "seaturtle", "hatchling", "ridley", "chelonia", "caretta", "turtle baby", "baby turtle", "turtle release")):
            reason = "title does not establish sea-turtle hatchling relevance"
        elif role == "negative" and kind == "image" and "hatchling" in lower:
            reason = "negative search returned a hatchling"
        elif role == "negative" and kind == "image" and "crab" in lower and not any(x in lower for x in ("beach", "sand", "shore")):
            reason = "crab scene not visibly linked to beach by title"
        elif kind == "video" and title not in POSITIVE_VIDEO_TITLES + NEGATIVE_VIDEO_TITLES:
            reason = "video not manually screened for task relevance"

        # Avoid filling the collection with one event or uploader.
        prefix = re.sub(r"\d+", "", lower.split("(")[0]).strip()[:38]
        series_key = (role, prefix)
        if not reason and kind == "image" and series[series_key] >= 4:
            reason = "same-title series cap (potential correlated event)"
        if not reason and counts[(role, kind)] >= {("positive", "image"): 85, ("negative", "image"): 35,
                                                ("positive", "video"): 7, ("negative", "video"): 3}[(role, kind)]:
            reason = "collection target reached"
        use_thumb = kind == "image" and info.get("thumburl") and info.get("thumbwidth", 0) < info.get("width", 0)
        record = {"title": title, "role": role, "kind": kind or "", "source_page": info.get("descriptionurl", ""),
                  "direct_url": info.get("url", ""), "license": license_name, "license_url": license_url,
                  "download_url": info.get("thumburl") if use_thumb else info.get("url", ""),
                  "media_variant": "Wikimedia 1280px derivative" if use_thumb else "source original",
                  "creator": field(meta, "Artist"), "credit": field(meta, "Credit"),
                  "description": field(meta, "ImageDescription"), "date_original": field(meta, "DateTimeOriginal"),
                  "commons_sha1": info.get("sha1", ""), "commons_size_bytes": size,
                  "search_query": candidates[title]["search_query"], "download_date": date.today().isoformat(),
                  "source_organization": "Wikimedia Commons (original creator in creator/credit)",
                  "group_id": prefix or str(page["pageid"]), "license_review": "Commons metadata; verify attribution on source page before sharing"}
        if reason:
            rejected.append({**record, "reason": reason})
            continue
        series[series_key] += 1
        counts[(role, kind)] += 1
        selected.append(record)
      selected_cache.write_text(json.dumps(selected, indent=2, ensure_ascii=False), encoding="utf-8")
    print("selected", dict(counts), "rejected", len(rejected), flush=True)

    accepted = []
    seen_sha = {}
    for index, record in enumerate(selected, 1):
        title = record["title"]
        page_id_match = re.search(r"curid=(\d+)", record["source_page"])
        # Page ID from stable Commons description URL is usually absent; URL is
        # still stable because the filename is appended to this normalized slug.
        base = unicodedata.normalize("NFKD", Path(title.removeprefix("File:")).stem).encode("ascii", "ignore").decode()
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", base).strip("_").lower()[:78]
        suffix = hashlib.sha1(title.encode()).hexdigest()[:8]
        ext = Path(title).suffix.lower()
        subdir = "negatives" if record["role"] == "negative" else "originals"
        existing_original = OUT / subdir / ("videos" if record["kind"] == "video" else "images") / f"{slug}_{suffix}{ext}"
        if existing_original.exists():
            record["media_variant"] = "source original"
            record["download_url"] = record["direct_url"]
        if record.get("media_variant") == "Wikimedia 1280px derivative":
            subdir = "derivatives" if record["role"] == "positive" else "negative_derivatives"
        path = OUT / subdir / ("videos" if record["kind"] == "video" else "images") / f"{slug}_{suffix}{ext}"
        try:
            # Commons explicitly asks rate-limited clients to use thumbnails.
            # Space CDN requests and keep a full provenance record for derivatives.
            time.sleep(5)
            expected_size = None if record.get("media_variant") == "Wikimedia 1280px derivative" else record["commons_size_bytes"]
            download(session, record.get("download_url", record["direct_url"]), path, expected_size)
            local_sha1 = checksum(path, "sha1")
            if expected_size is not None and local_sha1 != record["commons_sha1"]:
                raise ValueError("Commons SHA-1 mismatch")
            sha256 = checksum(path, "sha256")
            if sha256 in seen_sha:
                path.unlink(missing_ok=True)
                rejected.append({**record, "reason": f"exact duplicate of {seen_sha[sha256]}"})
                continue
            media = decode(path, record["kind"])
            seen_sha[sha256] = str(path.relative_to(ROOT))
            accepted.append({**record, **media, "local_path": str(path.relative_to(ROOT)), "sha256": sha256,
                             "size_bytes": path.stat().st_size, "decode_verified": True})
            print(f"{index}/{len(selected)} OK {path.name}", flush=True)
        except Exception as exc:
            path.unlink(missing_ok=True)
            rejected.append({**record, "reason": f"download or verification failed: {exc}"})
            print(f"{index}/{len(selected)} REJECT {title}: {exc}", flush=True)
            if "429" in str(exc):
                print("Stopping to respect Wikimedia rate limit", flush=True)
                break

    (MANIFESTS / "media_manifest.json").write_text(json.dumps(accepted, indent=2, ensure_ascii=False), encoding="utf-8")
    (MANIFESTS / "rejected_candidates.json").write_text(json.dumps(rejected, indent=2, ensure_ascii=False), encoding="utf-8")
    if accepted:
        with (MANIFESTS / "media_manifest.csv").open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(accepted[0]))
            writer.writeheader(); writer.writerows(accepted)
    with (MANIFESTS / "rejected_candidates.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rejected[0]) if rejected else ["title", "reason"])
        writer.writeheader(); writer.writerows(rejected)
    print("FINAL", len(accepted), "accepted", len(rejected), "rejected", flush=True)


if __name__ == "__main__":
    main()
