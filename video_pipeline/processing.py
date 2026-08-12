"""Runs one clip through the editing chain.

Two stages:

1. auto-editor removes silence / dead space (optional).
2. ffmpeg crops to vertical 9:16, normalizes to H.264/AAC yuv420p, and
   composites optional caption/watermark text.

Text is rendered with Pillow into a transparent PNG and applied with
ffmpeg's ``overlay`` filter — the static ffmpeg shipped by the
imageio-ffmpeg wheel has no ``drawtext``/freetype support, so drawing
the text ourselves keeps the whole toolchain pip-installable.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from .config import Config

log = logging.getLogger(__name__)

_DIMENSIONS_RE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")


def _run(cmd: list[str], step: str) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"{step} failed (exit {result.returncode}):\n{tail}")
    return result


def probe_dimensions(path: Path) -> tuple[int, int]:
    # ``ffmpeg -i`` exits non-zero with no output file, but still prints
    # stream info; imageio-ffmpeg ships no ffprobe, so parse that.
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    match = _DIMENSIONS_RE.search(result.stderr)
    if not match:
        raise RuntimeError(f"Could not determine video dimensions of {path.name}")
    return int(match.group(1)), int(match.group(2))


def _load_font(cfg: Config, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    if cfg.font_file is not None:
        try:
            return ImageFont.truetype(str(cfg.font_file), size=size)
        except OSError:
            log.warning("Could not load font %s; using built-in font", cfg.font_file)
    return ImageFont.load_default(size=size)


def render_text_overlay(cfg: Config, size: tuple[int, int], destination: Path) -> Path:
    """Draw caption/watermark onto a transparent canvas sized to the video."""
    width, height = size
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if cfg.caption:
        draw.text(
            (width / 2, height / 10),
            cfg.caption,
            font=_load_font(cfg, size=height // 18),
            fill=(255, 255, 255, 255),
            stroke_width=max(2, height // 480),
            stroke_fill=(0, 0, 0, 255),
            anchor="ma",
        )
    if cfg.watermark:
        draw.text(
            (width - width // 30, height - height // 40),
            cfg.watermark,
            font=_load_font(cfg, size=height // 40),
            fill=(255, 255, 255, 153),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 153),
            anchor="rd",
        )
    image.save(destination)
    return destination


def _base_filter(cfg: Config) -> list[str]:
    if not cfg.vertical:
        return []
    # Center-crop to the target aspect ratio; min() keeps
    # already-vertical footage intact.
    return [
        f"crop='min(iw,ih*{cfg.width}/{cfg.height})':ih",
        f"scale={cfg.width}:{cfg.height}:flags=lanczos",
        "setsar=1",
    ]


def _output_path(source: Path, cfg: Config) -> Path:
    base = f"{source.stem}{cfg.suffix}"
    candidate = cfg.output_dir / f"{base}.mp4"
    counter = 1
    while candidate.exists():
        candidate = cfg.output_dir / f"{base}-{counter}.mp4"
        counter += 1
    return candidate


def process(source: Path, cfg: Config) -> Path:
    """Edit one clip and return the path of the finished file."""
    out_path = _output_path(source, cfg)
    with tempfile.TemporaryDirectory(prefix="video_pipeline_") as tmp:
        tmpdir = Path(tmp)
        current = source

        if cfg.silence_cut:
            cut = tmpdir / "cut.mp4"
            _run(
                [
                    sys.executable, "-m", "auto_editor", str(source),
                    "--margin", cfg.margin,
                    "--no-open",
                    "-o", str(cut),
                ],
                "auto-editor",
            )
            current = cut

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y",
            "-hide_banner", "-loglevel", "error",
            "-i", str(current),
        ]
        if cfg.caption or cfg.watermark:
            overlay_size = (cfg.width, cfg.height) if cfg.vertical else probe_dimensions(current)
            overlay = render_text_overlay(cfg, overlay_size, tmpdir / "overlay.png")
            chain = ",".join([*_base_filter(cfg), "null"])
            cmd += [
                "-i", str(overlay),
                "-filter_complex",
                f"[0:v]{chain}[base];[base][1:v]overlay=0:0,format=yuv420p[out]",
                "-map", "[out]", "-map", "0:a?",
            ]
        else:
            cmd += ["-vf", ",".join([*_base_filter(cfg), "format=yuv420p"])]
        encoded = tmpdir / out_path.name
        cmd += [
            "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf),
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(encoded),
        ]
        _run(cmd, "ffmpeg")

        # Encode outside the synced folder, then move the finished file
        # in, so OneDrive never uploads a half-written video.
        shutil.move(str(encoded), out_path)
    return out_path
