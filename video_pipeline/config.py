"""Pipeline configuration.

Every option can come from an environment variable (``VP_*``) or a CLI
flag; flags win. Paths default to the conventional OneDrive layout on
the user's machine but nothing is OneDrive-specific — any folder works.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mts", ".3gp"}

# Files the OneDrive client (or a camera import) writes while a transfer
# is still in flight.
IGNORED_SUFFIXES = (".tmp", ".partial", ".crdownload", ".part")
IGNORED_PREFIXES = ("~", ".")

_FONT_CANDIDATES = {
    "win32": [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ],
    "darwin": [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ],
    "linux": [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ],
}


def find_font() -> Path | None:
    """Best-effort lookup of a system font usable by ffmpeg drawtext."""
    platform = "linux"
    if sys.platform.startswith("win"):
        platform = "win32"
    elif sys.platform == "darwin":
        platform = "darwin"
    for candidate in _FONT_CANDIDATES[platform]:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _env(name: str, default: str) -> str:
    return os.environ.get(f"VP_{name}", default)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(f"VP_{name}")
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


@dataclass
class Config:
    watch_dir: Path = field(
        default_factory=lambda: Path(_env("WATCH_DIR", str(Path.home() / "OneDrive" / "Videos" / "Inbox")))
    )
    output_dir: Path = field(
        default_factory=lambda: Path(_env("OUTPUT_DIR", str(Path.home() / "OneDrive" / "Videos" / "Edited")))
    )

    # Editing options
    silence_cut: bool = field(default_factory=lambda: _env_bool("SILENCE_CUT", True))
    margin: str = field(default_factory=lambda: _env("MARGIN", "0.2sec"))
    vertical: bool = field(default_factory=lambda: _env_bool("VERTICAL", True))
    width: int = field(default_factory=lambda: int(_env("WIDTH", "1080")))
    height: int = field(default_factory=lambda: int(_env("HEIGHT", "1920")))
    caption: str = field(default_factory=lambda: _env("CAPTION", ""))
    watermark: str = field(default_factory=lambda: _env("WATERMARK", ""))
    font_file: Path | None = field(
        default_factory=lambda: Path(os.environ["VP_FONT"]) if os.environ.get("VP_FONT") else None
    )

    # Encoding
    crf: int = field(default_factory=lambda: int(_env("CRF", "20")))
    preset: str = field(default_factory=lambda: _env("PRESET", "veryfast"))
    suffix: str = field(default_factory=lambda: _env("SUFFIX", "_edited"))

    # Watcher behavior. stable_seconds guards against processing a file
    # the OneDrive client is still writing.
    stable_seconds: float = field(default_factory=lambda: float(_env("STABLE_SECONDS", "5")))
    poll_interval: float = field(default_factory=lambda: float(_env("POLL_INTERVAL", "2")))

    def validate(self) -> None:
        if not self.watch_dir.is_dir():
            raise SystemExit(
                f"Watch folder does not exist: {self.watch_dir}\n"
                "Create it, or point the pipeline at your OneDrive folder with "
                "--watch-dir (or the VP_WATCH_DIR environment variable)."
            )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.watch_dir.resolve() == self.output_dir.resolve():
            raise SystemExit("Watch folder and output folder must be different.")
        if (self.caption or self.watermark) and self.font_file is None:
            self.font_file = find_font()
