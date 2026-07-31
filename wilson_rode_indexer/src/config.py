"""Configuration loading, validation and path resolution.

The entire behaviour of the indexer is driven by ``config.yaml``.  This module
loads that file, applies defaults, validates the values that would otherwise
fail deep inside a worker process, and resolves the two paths that matter most:
the read-only source folder and the derived-index output folder.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

DEFAULT_CONFIG_NAME = "config.yaml"


class ConfigError(RuntimeError):
    """Raised when the configuration file is missing, unreadable or invalid."""


@dataclass
class FolderCandidate:
    """A directory that matched the configured source-folder name."""

    path: Path
    file_count: int
    pdf_count: int
    total_bytes: int

    def describe(self) -> str:
        """Return a single-line human-readable summary (no file contents)."""
        gib = self.total_bytes / (1024**3)
        return (
            f"{self.path}  "
            f"[{self.file_count} files, {self.pdf_count} PDFs, {gib:.2f} GiB]"
        )


class Config:
    """Parsed configuration with convenience accessors.

    Parameters
    ----------
    data:
        The raw mapping loaded from YAML.
    config_path:
        Location the mapping was loaded from; used to resolve relative paths
        and to record provenance in the audit log.
    """

    def __init__(self, data: Dict[str, Any], config_path: Path) -> None:
        self._data = data
        self.config_path = config_path
        self.project_root = config_path.parent
        self._validate()

    # ------------------------------------------------------------------
    # loading
    # ------------------------------------------------------------------
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load configuration from ``config_path`` (default ``./config.yaml``)."""
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / DEFAULT_CONFIG_NAME
        config_path = Path(config_path).expanduser().resolve()
        if not config_path.is_file():
            raise ConfigError(f"Configuration file not found: {config_path}")
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except yaml.YAMLError as exc:  # pragma: no cover - defensive
            raise ConfigError(f"Could not parse {config_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{config_path} must contain a YAML mapping")
        return cls(data, config_path)

    # ------------------------------------------------------------------
    # generic access
    # ------------------------------------------------------------------
    def get(self, *keys: str, default: Any = None) -> Any:
        """Return a nested configuration value, or ``default`` if absent."""
        node: Any = self._data
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def section(self, name: str) -> Dict[str, Any]:
        """Return a top-level section as a dictionary (never ``None``)."""
        value = self._data.get(name)
        return value if isinstance(value, dict) else {}

    @property
    def raw(self) -> Dict[str, Any]:
        """The underlying mapping.  Treat as read-only."""
        return self._data

    # ------------------------------------------------------------------
    # validation
    # ------------------------------------------------------------------
    def _validate(self) -> None:
        """Fail fast on values that would otherwise break a worker process."""
        problems: List[str] = []

        for key in ("filename_regex", "page_regex", "filename_pattern"):
            pattern = self.get("bates", key)
            if not pattern:
                problems.append(f"bates.{key} is required")
                continue
            try:
                re.compile(pattern)
            except re.error as exc:
                problems.append(f"bates.{key} is not a valid regex: {exc}")

        for name, patterns in (self.get("classification", "rules") or {}).items():
            for pattern in (patterns or {}).get("patterns", []):
                try:
                    re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                except re.error as exc:
                    problems.append(
                        f"classification.rules.{name} has an invalid pattern: {exc}"
                    )

        for pattern in self.get("email", "chain_separators") or []:
            try:
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
            except re.error as exc:
                problems.append(f"email.chain_separators invalid pattern: {exc}")

        for pattern in self.get("duplicates", "normalize_strip_patterns") or []:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                problems.append(
                    f"duplicates.normalize_strip_patterns invalid pattern: {exc}"
                )

        bits = int(self.get("duplicates", "simhash_bits", default=64))
        bands = int(self.get("duplicates", "simhash_bands", default=8))
        if bits <= 0 or bands <= 0 or bits % bands != 0:
            problems.append(
                "duplicates.simhash_bits must be a positive multiple of "
                "duplicates.simhash_bands"
            )

        tags = self.issue_tags()
        if not isinstance(tags, dict):
            problems.append("issue_tags must be a mapping of TAG -> [terms]")
        else:
            for tag, terms in tags.items():
                if not isinstance(terms, list) or not terms:
                    problems.append(f"issue_tags.{tag} must be a non-empty list")

        if problems:
            raise ConfigError(
                "Invalid configuration in "
                f"{self.config_path}:\n  - " + "\n  - ".join(problems)
            )

    # ------------------------------------------------------------------
    # paths
    # ------------------------------------------------------------------
    def configured_source_folder(self) -> Optional[Path]:
        """Return the explicitly configured source folder, if any."""
        raw = self.get("paths", "source_folder")
        if not raw:
            return None
        return Path(str(raw)).expanduser()

    def source_folder_name(self) -> str:
        """Name of the production folder to look for when auto-detecting."""
        return str(self.get("paths", "source_folder_name", default="Wilson-Rode File"))

    def output_folder_name(self) -> str:
        """Name of the derived-index folder created beside the source."""
        return str(
            self.get("paths", "output_folder_name", default="Wilson_Rode_Derived_Index")
        )

    def search_roots(self) -> List[Path]:
        """Existing directories that will be scanned when auto-detecting."""
        roots: List[Path] = []
        for raw in self.get("paths", "search_roots") or []:
            candidate = Path(str(raw)).expanduser()
            if candidate.is_dir():
                roots.append(candidate)
        return roots

    def resolve_source_folder(self, override: Optional[Path] = None) -> Path:
        """Resolve the read-only source folder.

        Precedence: ``override`` argument, then ``paths.source_folder`` in the
        configuration file.  Auto-detection is deliberately *not* performed
        here -- it lives in :mod:`src.inventory` so that the CLI can present
        multiple candidates for the operator to choose between.

        Raises
        ------
        ConfigError
            If no source folder is known, or the path is not a directory.
        """
        chosen = Path(override).expanduser() if override else self.configured_source_folder()
        if chosen is None:
            raise ConfigError(
                "No source folder configured.  Run `wri locate` to find it, then "
                "set paths.source_folder in config.yaml or pass --source."
            )
        chosen = chosen.resolve()
        if not chosen.is_dir():
            raise ConfigError(f"Source folder is not a directory: {chosen}")
        return chosen

    def resolve_output_folder(
        self, source: Path, override: Optional[Path] = None
    ) -> Path:
        """Resolve the derived-index folder.

        The output folder is always a *sibling* of the source folder unless the
        operator overrides it.  It is never permitted to live inside the source
        folder, which would violate the read-only guarantee.
        """
        if override:
            out = Path(override).expanduser().resolve()
        else:
            configured = self.get("paths", "output_folder")
            if configured:
                out = Path(str(configured)).expanduser().resolve()
            else:
                out = (source.parent / self.output_folder_name()).resolve()

        if out == source or _is_within(out, source):
            raise ConfigError(
                "Refusing to write inside the read-only source folder.\n"
                f"  source: {source}\n  output: {out}"
            )
        return out

    # ------------------------------------------------------------------
    # frequently used sections
    # ------------------------------------------------------------------
    def issue_tags(self) -> Dict[str, List[str]]:
        """Return the issue-tag dictionary (``TAG -> [terms]``)."""
        return self.section("issue_tags")

    def worker_count(self) -> int:
        """Return the effective worker count, clamped and CPU-aware."""
        requested = int(self.get("performance", "workers", default=4) or 4)
        ceiling = int(self.get("performance", "max_workers", default=8) or 8)
        cpu = os.cpu_count() or 2
        return max(1, min(requested, ceiling, max(1, cpu - 1)))

    def ocr_enabled(self) -> bool:
        """Whether OCR is permitted at all."""
        return bool(self.get("ocr", "enabled", default=False))


def _is_within(candidate: Path, parent: Path) -> bool:
    """Return ``True`` when ``candidate`` is inside ``parent``."""
    try:
        candidate.relative_to(parent)
    except ValueError:
        return False
    return True


def summarize_candidates(candidates: Iterable[FolderCandidate]) -> str:
    """Format folder candidates for terminal display (paths only, no content)."""
    lines = []
    for index, candidate in enumerate(candidates, start=1):
        lines.append(f"  [{index}] {candidate.describe()}")
    return "\n".join(lines) if lines else "  (none found)"
