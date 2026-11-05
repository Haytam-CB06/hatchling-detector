"""Open the local FiftyOne review app for a named Nazar Vision dataset.

Usage (PowerShell, after `conda activate nazar-vision`):
    python scripts/open_fiftyone.py
    python scripts/open_fiftyone.py --dataset my_dataset
    python scripts/open_fiftyone.py --port 5152
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_DIR = PROJECT_ROOT / "data" / "fiftyone_db"
DATABASE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("FIFTYONE_DATABASE_DIR", str(DATABASE_DIR))

import fiftyone as fo  # noqa: E402  # The database location must be set first.


def main() -> None:
    # Windows terminals using cp1252 cannot encode FiftyOne's Unicode banner.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="nazar_vision_setup_check")
    parser.add_argument("--port", type=int, default=5151, help="Local FiftyOne web port (default: 5151)")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    if fo.dataset_exists(args.dataset):
        dataset = fo.load_dataset(args.dataset)
    else:
        dataset = fo.Dataset(args.dataset)
        dataset.persistent = True

    print(f"Dataset: {dataset.name} ({len(dataset)} samples)", flush=True)
    session = fo.launch_app(dataset, auto=False, port=args.port)
    print(f"Open {session.url} in your browser. Keep this terminal open; press Ctrl+C to stop.", flush=True)
    session.wait(-1)


if __name__ == "__main__":
    main()
