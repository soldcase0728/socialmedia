"""Flat JSON persistence.

Deliberately boring: a directory of JSON files that a human can open, read and
correct. No database to administer, no vendor, no migration. Point
BRANDOPS_DATA at a synced SharePoint/OneDrive folder and the whole team shares
one state.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data"

COLLECTIONS = ("assets", "queue", "results", "memory", "calendar", "published")


def data_dir() -> Path:
    return Path(os.environ.get("BRANDOPS_DATA", DEFAULT_DIR))


def path_for(name: str) -> Path:
    return data_dir() / f"{name}.json"


def load(name: str, default: Any = None) -> Any:
    path = path_for(name)
    if not path.exists():
        return default if default is not None else {}
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def save(name: str, payload: Any) -> Path:
    """Write atomically so an interrupted run never truncates the file."""
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = path_for(name)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, delete=False, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        temp = Path(handle.name)
    temp.replace(path)
    return path


def append(name: str, key: str, item: Any) -> Any:
    payload = load(name, {})
    payload.setdefault(key, []).append(item)
    save(name, payload)
    return payload
