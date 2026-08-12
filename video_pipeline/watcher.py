"""Folder watching and the processing loop.

The OneDrive client writes files incrementally, so a clip is only
processed once its size and mtime have stayed unchanged for
``stable_seconds``. Watchdog events feed a pending map; a simple poll
loop promotes stable entries to processing.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from . import processing
from .config import IGNORED_PREFIXES, IGNORED_SUFFIXES, VIDEO_EXTENSIONS, Config
from .ledger import Ledger

log = logging.getLogger(__name__)


def is_candidate(path: Path, cfg: Config) -> bool:
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        return False
    name = path.name
    if name.startswith(IGNORED_PREFIXES) or name.lower().endswith(IGNORED_SUFFIXES):
        return False
    try:
        if path.resolve().is_relative_to(cfg.output_dir.resolve()):
            return False
    except OSError:
        return False
    return True


def _signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, int(stat.st_mtime))


def process_file(source: Path, cfg: Config, ledger: Ledger) -> bool:
    log.info("Processing %s", source.name)
    started = time.monotonic()
    try:
        output = processing.process(source, cfg)
    except Exception:
        log.exception("Failed to process %s", source.name)
        return False
    ledger.mark_done(source, output)
    log.info("Done: %s -> %s (%.0fs)", source.name, output.name, time.monotonic() - started)
    return True


def find_backlog(cfg: Config, ledger: Ledger) -> list[Path]:
    return sorted(
        path
        for path in cfg.watch_dir.rglob("*")
        if path.is_file() and is_candidate(path, cfg) and not ledger.is_done(path)
    )


def wait_stable(path: Path, cfg: Config, timeout: float = 900) -> bool:
    """Block until the file stops changing; False if it vanishes or times out."""
    deadline = time.monotonic() + timeout
    last = _signature(path)
    stable_since = time.monotonic()
    while time.monotonic() < deadline:
        if last is None:
            return False
        if time.monotonic() - stable_since >= cfg.stable_seconds:
            return True
        time.sleep(cfg.poll_interval)
        current = _signature(path)
        if current != last:
            last = current
            stable_since = time.monotonic()
    return False


def run_once(cfg: Config, ledger: Ledger) -> int:
    """Process the current backlog and return the number of successes."""
    backlog = find_backlog(cfg, ledger)
    if not backlog:
        log.info("Nothing to process in %s", cfg.watch_dir)
        return 0
    log.info("Found %d clip(s) to process", len(backlog))
    done = 0
    for path in backlog:
        if wait_stable(path, cfg):
            done += int(process_file(path, cfg, ledger))
        else:
            log.warning("Skipping %s: file kept changing or disappeared", path.name)
    return done


class _Collector(FileSystemEventHandler):
    """Records paths touched by filesystem events; the main loop decides when they're ready."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.touched: dict[Path, None] = {}

    def _note(self, raw_path: str) -> None:
        path = Path(raw_path)
        if is_candidate(path, self.cfg):
            self.touched[path] = None

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._note(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._note(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._note(event.dest_path)


def run_watch(cfg: Config, ledger: Ledger) -> None:
    # Start collecting events before the backlog scan so clips that
    # arrive mid-scan aren't missed; the ledger check below keeps
    # anything from being processed twice.
    collector = _Collector(cfg)
    observer = Observer()
    observer.schedule(collector, str(cfg.watch_dir), recursive=True)
    observer.start()

    run_once(cfg, ledger)
    log.info("Watching %s (Ctrl+C to stop)", cfg.watch_dir)

    # path -> (last signature, time that signature was first seen)
    pending: dict[Path, tuple[tuple[int, int] | None, float]] = {}
    try:
        while True:
            time.sleep(cfg.poll_interval)
            for path in list(collector.touched):
                del collector.touched[path]
                if path not in pending:
                    pending[path] = (_signature(path), time.monotonic())
            for path, (sig, since) in list(pending.items()):
                current = _signature(path)
                if current is None:
                    del pending[path]
                elif current != sig:
                    pending[path] = (current, time.monotonic())
                elif time.monotonic() - since >= cfg.stable_seconds:
                    del pending[path]
                    if not ledger.is_done(path):
                        process_file(path, cfg, ledger)
    except KeyboardInterrupt:
        log.info("Stopping")
    finally:
        observer.stop()
        observer.join()
