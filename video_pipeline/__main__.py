"""CLI entry point: ``python -m video_pipeline``."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import Config
from .ledger import Ledger
from .watcher import find_backlog, run_once, run_watch


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="video_pipeline",
        description=(
            "Watch a OneDrive-synced folder for new clips, cut silence, "
            "crop to vertical 9:16, and write results to an output folder."
        ),
    )
    parser.add_argument("--watch-dir", type=Path, help="folder to watch for new clips")
    parser.add_argument("--output-dir", type=Path, help="folder for edited clips")
    parser.add_argument("--once", action="store_true", help="process the backlog and exit instead of watching")
    parser.add_argument("--dry-run", action="store_true", help="list what would be processed, then exit")
    parser.add_argument("--caption", help="text overlaid near the top of every clip")
    parser.add_argument("--watermark", help="small text in the bottom-right corner")
    parser.add_argument("--margin", help="silence-cut padding around kept audio (default 0.2sec)")
    parser.add_argument("--no-silence-cut", action="store_true", help="skip the auto-editor silence-cut stage")
    parser.add_argument("--no-vertical", action="store_true", help="keep the original aspect ratio")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = Config()
    if args.watch_dir:
        cfg.watch_dir = args.watch_dir
    if args.output_dir:
        cfg.output_dir = args.output_dir
    if args.caption is not None:
        cfg.caption = args.caption
    if args.watermark is not None:
        cfg.watermark = args.watermark
    if args.margin is not None:
        cfg.margin = args.margin
    if args.no_silence_cut:
        cfg.silence_cut = False
    if args.no_vertical:
        cfg.vertical = False
    cfg.validate()

    ledger = Ledger(cfg.output_dir / ".processed.json")

    if args.dry_run:
        backlog = find_backlog(cfg, ledger)
        if backlog:
            print(f"Would process {len(backlog)} clip(s):")
            for path in backlog:
                print(f"  {path}")
        else:
            print(f"Nothing to process in {cfg.watch_dir}")
        return

    if args.once:
        run_once(cfg, ledger)
    else:
        run_watch(cfg, ledger)


if __name__ == "__main__":
    main()
