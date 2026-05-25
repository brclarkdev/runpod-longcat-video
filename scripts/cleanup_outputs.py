#!/usr/bin/env python3
import argparse
import os
import shutil
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=os.environ.get("LONGCAT_OUTPUT_DIR", "outputs"))
    parser.add_argument("--older-than-hours", type=float, default=48)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    root = Path(args.output_dir)
    if not root.exists():
        print(f"No output dir: {root}")
        return 0
    cutoff = time.time() - args.older_than_hours * 3600
    removed = 0
    for child in root.iterdir():
        if child.name in {"models", "LongCat-Video"}:
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            print(f"remove {child}")
            if not args.dry_run:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            removed += 1
    print(f"Removed {removed} items" if not args.dry_run else f"Would remove {removed} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
