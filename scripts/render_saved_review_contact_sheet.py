"""Render saved annotation drafts for visual QA without changing source media."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app import config
from backend.app.review import ReviewStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    store = ReviewStore(
        config.REVIEW_MANIFEST,
        config.REVIEW_PREDICTIONS,
        config.REVIEW_DB,
        config.REVIEW_EXPORTS,
        config.REVIEW_TRAIN_MANIFEST,
        config.REVIEW_TRAIN_PREDICTIONS,
    )
    with sqlite3.connect(config.REVIEW_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM reviews ORDER BY reviewed_at").fetchall()
    if not rows:
        raise SystemExit("No saved reviews")

    tile_w, tile_h, columns = 760, 570, 2
    sheet = Image.new("RGB", (tile_w * columns, tile_h * ((len(rows) + columns - 1) // columns)), "#18232a")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, row in enumerate(rows):
        item = store.items[row["image_id"]]
        with Image.open(item["path"]) as original:
            picture = original.convert("RGB")
        picture.thumbnail((tile_w - 20, tile_h - 92))
        ox = (index % columns) * tile_w + (tile_w - picture.width) // 2
        oy = (index // columns) * tile_h + 60
        sheet.paste(picture, (ox, oy))
        draw.text((index % columns * tile_w + 10, index // columns * tile_h + 10),
                  f"{item['filename']} | {row['status']}", fill="white", font=font)
        sx, sy = picture.width / item["width"], picture.height / item["height"]
        for box in json.loads(row["boxes_json"]):
            x1, y1, x2, y2 = box["xyxy"]
            color = "#00ff85" if box["class_name"] == "hatchling" else "#ffbb00"
            draw.rectangle((ox + x1 * sx, oy + y1 * sy, ox + x2 * sx, oy + y2 * sy), outline=color, width=3)
            draw.text((ox + x1 * sx, max(oy, oy + y1 * sy - 14)), box["class_name"], fill=color, font=font)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
