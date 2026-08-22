"""Shared fixtures. Every test that touches the store gets its own directory."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brandops.assets import Asset, from_intake  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("BRANDOPS_DATA", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture
def lab_video() -> Asset:
    return from_intake({
        "event": "AP Chemistry lab",
        "department": "Science",
        "contributor": "Mr. Kowalski",
        "description": "candid: two students titrating, one explains the reaction",
        "filename": "IMG_0001.mov",
        "captured_at": "2026-08-24",
        "subjects": "Marcus Bell",
        "duration_s": 14,
        "orientation": "vertical",
        "possible_story": "They ran it twice because the first run was off by 0.4 mL",
    })


@pytest.fixture
def mass_photo() -> Asset:
    return from_intake({
        "event": "All-School Mass",
        "department": "Campus Ministry",
        "contributor": "Fr. Nowak",
        "description": "students singing during the recessional",
        "filename": "IMG_0002.jpg",
        "captured_at": "2026-08-24",
        "orientation": "horizontal",
    })


@pytest.fixture
def today() -> date:
    return date(2026, 8, 24)
