"""Tracks which source files have already been processed.

A JSON file keyed by absolute source path, storing the size/mtime the
file had when it was processed — so a re-uploaded or re-recorded file
with the same name gets processed again, while an unchanged file is
skipped across restarts.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, dict] = {}
        if path.is_file():
            try:
                self._entries = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.warning("Could not read ledger %s; starting fresh", path)

    @staticmethod
    def _signature(source: Path) -> dict:
        stat = source.stat()
        return {"size": stat.st_size, "mtime": int(stat.st_mtime)}

    def is_done(self, source: Path) -> bool:
        entry = self._entries.get(str(source.resolve()))
        if not entry:
            return False
        try:
            sig = self._signature(source)
        except OSError:
            return False
        return entry.get("size") == sig["size"] and entry.get("mtime") == sig["mtime"]

    def mark_done(self, source: Path, output: Path) -> None:
        entry = self._signature(source)
        entry["output"] = str(output)
        self._entries[str(source.resolve())] = entry
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self._entries, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
