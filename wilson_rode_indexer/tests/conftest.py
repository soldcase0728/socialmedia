"""Shared pytest fixtures.

The fixtures build a small synthetic production so the full pipeline can be
exercised without touching any real document.  Nothing in the tests reads or
writes the real source folder.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config  # noqa: E402
from src.database import Database  # noqa: E402


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Path to the project root."""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def config(project_root: Path) -> Config:
    """The project's real configuration, loaded fresh."""
    return Config.load(project_root / "config.yaml")


@pytest.fixture
def database(tmp_path: Path) -> Database:
    """An empty processing database in a temporary directory."""
    db = Database(tmp_path / "test.sqlite")
    yield db
    db.close()


@pytest.fixture
def make_pdf() -> Callable[..., Path]:
    """Return a factory that writes a small PDF for testing.

    The factory takes a destination path and a list of per-page text blocks.
    A page whose text is ``None`` is left empty, which is how blank-page
    handling is tested.
    """
    fitz = pytest.importorskip("fitz")

    def _make(
        path: Path,
        pages: List[Optional[str]],
        *,
        bates_start: Optional[int] = None,
        bates_prefix: str = "WILSONRODE",
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        for index, text in enumerate(pages):
            page = document.new_page(width=612, height=792)
            if text:
                page.insert_text((72, 100), text, fontsize=10)
            if bates_start is not None:
                page.insert_text(
                    (420, 760), f"{bates_prefix}{bates_start + index:06d}", fontsize=8
                )
        document.save(str(path))
        document.close()
        return path

    return _make


@pytest.fixture
def sample_production(tmp_path: Path, make_pdf) -> Path:
    """A tiny synthetic production covering the interesting cases."""
    source = tmp_path / "Wilson-Rode File"
    source.mkdir(parents=True, exist_ok=True)

    make_pdf(
        source / "WILSONRODE000001-null.pdf",
        [
            "From: John Wilson <jwilson@example.com>\n"
            "Sent: March 4, 2019 9:15 AM\n"
            "To: Patrick Rode <prode@example.com>\n"
            "Cc: Legal Team <legal@example.com>\n"
            "Subject: Commission agreement question\n"
            "Attachments: Agreement_Draft.pdf\n\n"
            "Pat, please review the commission agreement before Friday."
        ],
        bates_start=1,
    )
    make_pdf(
        source / "WILSONRODE000002-null.pdf",
        [
            "COMMISSION AGREEMENT\n\nWHEREAS the parties agree that residual "
            "commission shall continue for the lifetime of the account.\n"
            "NOW THEREFORE the parties hereto agree as follows."
        ],
        bates_start=2,
    )
    make_pdf(source / "WILSONRODE000003-null.pdf", [None], bates_start=3)
    make_pdf(
        source / "WILSONRODE000010-null.pdf",
        [
            "IN THE CIRCUIT COURT FOR THE COUNTY OF WAYNE\n"
            "STATE OF MICHIGAN\n"
            "Case No. 2020-123456-CB\n"
            "Plaintiff v. Defendant\n"
            "ANSWER AND AFFIRMATIVE DEFENSES\n"
            "The statute of frauds bars the claim.",
            "Page two of the answer. Leave to amend is requested.",
        ],
        bates_start=10,
    )
    # A byte-identical duplicate, produced by copying rather than regenerating.
    duplicate = source / "WILSONRODE000020-null.pdf"
    duplicate.write_bytes((source / "WILSONRODE000002-null.pdf").read_bytes())
    # A file whose name does not match the production pattern.
    make_pdf(source / "scan_0001.pdf", ["An unnamed scanned document."])
    return source


@pytest.fixture
def configured(tmp_path: Path, sample_production: Path, project_root: Path):
    """Config, database, source and output wired to the synthetic production."""
    import yaml

    raw = yaml.safe_load((project_root / "config.yaml").read_text(encoding="utf-8"))
    raw["paths"]["source_folder"] = str(sample_production)
    raw["paths"]["output_folder"] = str(tmp_path / "Wilson_Rode_Derived_Index")
    raw["performance"]["workers"] = 1
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    config = Config.load(config_path)
    source = config.resolve_source_folder()
    output = config.resolve_output_folder(source)
    output.mkdir(parents=True, exist_ok=True)
    database = Database(output / "test.sqlite")
    yield config, database, source, output
    database.close()
