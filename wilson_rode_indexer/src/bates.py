"""Bates number parsing, normalisation, ranges, gaps and overlaps.

Every value produced here is *derived*.  A Bates number parsed from a filename
is weaker evidence than one observed printed on a page, and the two are kept
distinct throughout so that reports can state which is which.

Confidence vocabulary
---------------------
``confirmed``
    Observed on the page itself and consistent with the filename (or observed
    on both the first and last page of a multi-page document).
``probable``
    Observed on the page but only on some pages, or observed without a
    corroborating filename.
``possible``
    Parsed from the filename only, or calculated by page arithmetic.
``unknown``
    Nothing usable was found.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------
SOURCE_OBSERVED = "observed_on_page"
SOURCE_FILENAME = "parsed_from_filename"
SOURCE_CALCULATED = "calculated"
SOURCE_INFERRED = "inferred"
SOURCE_NONE = "none"

CONF_CONFIRMED = "confirmed"
CONF_PROBABLE = "probable"
CONF_POSSIBLE = "possible"
CONF_UNKNOWN = "unknown"


@dataclass(frozen=True)
class BatesNumber:
    """A single parsed Bates number."""

    prefix: str
    number: int
    width: int

    @property
    def normalized(self) -> str:
        """Canonical form, e.g. ``WILSONRODE000123``."""
        return f"{self.prefix}{self.number:0{self.width}d}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.normalized


@dataclass
class BatesRange:
    """A begin/end Bates range with provenance."""

    begin: Optional[BatesNumber]
    end: Optional[BatesNumber]
    source: str = SOURCE_NONE
    confidence: str = CONF_UNKNOWN
    notes: List[str] = field(default_factory=list)

    @property
    def begin_str(self) -> Optional[str]:
        """Normalised begin Bates, or ``None``."""
        return self.begin.normalized if self.begin else None

    @property
    def end_str(self) -> Optional[str]:
        """Normalised end Bates, or ``None``."""
        return self.end.normalized if self.end else None

    @property
    def begin_num(self) -> Optional[int]:
        """Numeric begin Bates, or ``None``."""
        return self.begin.number if self.begin else None

    @property
    def end_num(self) -> Optional[int]:
        """Numeric end Bates, or ``None``."""
        return self.end.number if self.end else None

    @property
    def span(self) -> Optional[int]:
        """Number of Bates numbers covered, inclusive."""
        if self.begin is None or self.end is None:
            return None
        return self.end.number - self.begin.number + 1


class BatesParser:
    """Parses Bates numbers from filenames and from extracted page text.

    Parameters
    ----------
    filename_regex:
        Regex with one capturing group for the digits, applied to filenames.
    page_regex:
        Regex with one capturing group for the digits, applied to page text.
    prefix:
        Canonical prefix used when normalising.
    pad_width:
        Zero-padding width used when normalising.
    filename_pattern:
        Regex a filename must fully match to be "pattern compliant".
    """

    def __init__(
        self,
        filename_regex: str = r"WILSONRODE(\d+)",
        page_regex: str = r"WILSONRODE\s*[-_]?\s*(\d{4,10})",
        prefix: str = "WILSONRODE",
        pad_width: int = 6,
        filename_pattern: str = r"^WILSONRODE\d{6}-null\.pdf$",
    ) -> None:
        self.filename_re = re.compile(filename_regex, re.IGNORECASE)
        self.page_re = re.compile(page_regex, re.IGNORECASE)
        self.prefix = prefix
        self.pad_width = pad_width
        self.filename_pattern_re = re.compile(filename_pattern, re.IGNORECASE)

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, config) -> "BatesParser":
        """Build a parser from a :class:`src.config.Config`."""
        return cls(
            filename_regex=config.get("bates", "filename_regex",
                                      default=r"WILSONRODE(\d+)"),
            page_regex=config.get("bates", "page_regex",
                                  default=r"WILSONRODE\s*[-_]?\s*(\d{4,10})"),
            prefix=config.get("bates", "prefix", default="WILSONRODE"),
            pad_width=int(config.get("bates", "pad_width", default=6)),
            filename_pattern=config.get("bates", "filename_pattern",
                                        default=r"^WILSONRODE\d{6}-null\.pdf$"),
        )

    # ------------------------------------------------------------------
    def make(self, number: int) -> BatesNumber:
        """Construct a :class:`BatesNumber` in the configured canonical form."""
        return BatesNumber(self.prefix, int(number), self.pad_width)

    def parse_filename(self, filename: str) -> Optional[BatesNumber]:
        """Return the Bates number encoded in ``filename``, if any.

        Only the first match is used; production filenames carry exactly one.
        """
        match = self.filename_re.search(filename or "")
        if not match:
            return None
        digits = match.group(1)
        try:
            value = int(digits)
        except (TypeError, ValueError):  # pragma: no cover - regex guarantees digits
            return None
        return BatesNumber(self.prefix, value, max(self.pad_width, len(digits)))

    def is_filename_compliant(self, filename: str) -> bool:
        """Whether ``filename`` fully matches the configured naming pattern."""
        return bool(self.filename_pattern_re.match(filename or ""))

    def find_in_text(self, text: str, limit: int = 20) -> List[BatesNumber]:
        """Return Bates numbers appearing in ``text``, in order of appearance.

        Used on extracted page text.  The caller decides whether the page was
        searched footer-first; this function is position-agnostic.
        """
        found: List[BatesNumber] = []
        for match in self.page_re.finditer(text or ""):
            digits = match.group(1)
            try:
                value = int(digits)
            except (TypeError, ValueError):  # pragma: no cover
                continue
            found.append(BatesNumber(self.prefix, value, max(self.pad_width, len(digits))))
            if len(found) >= limit:
                break
        return found

    def find_on_page(
        self, page_text: str, footer_text: Optional[str] = None
    ) -> Optional[BatesNumber]:
        """Return the Bates stamp most likely printed on a page.

        The footer region is searched first because production stamps are
        applied there; the full page text is a fallback.  When several numbers
        appear in the footer the last one wins, matching the usual
        bottom-right stamp position.
        """
        if footer_text:
            footer_hits = self.find_in_text(footer_text)
            if footer_hits:
                return footer_hits[-1]
        hits = self.find_in_text(page_text)
        return hits[-1] if hits else None


# ---------------------------------------------------------------------------
# range assembly
# ---------------------------------------------------------------------------
def build_range(
    parser: BatesParser,
    *,
    filename_bates: Optional[BatesNumber],
    observed: Sequence[Optional[BatesNumber]],
    page_count: Optional[int],
) -> BatesRange:
    """Derive a document's begin/end Bates range with provenance.

    Parameters
    ----------
    parser:
        Parser supplying the canonical prefix and padding.
    filename_bates:
        Bates number parsed from the filename, if any.
    observed:
        Per-page observed stamps in page order.  Entries may be ``None`` where
        no stamp was found on that page.
    page_count:
        Number of pages in the document, used for calculated ranges.

    Returns
    -------
    BatesRange
        A range whose ``source`` and ``confidence`` describe exactly how the
        values were obtained.  Nothing is invented: when no evidence exists,
        the range is empty with ``unknown`` confidence.
    """
    seen = [b for b in observed if b is not None]
    notes: List[str] = []

    if seen:
        begin = min(seen, key=lambda b: b.number)
        end = max(seen, key=lambda b: b.number)
        coverage = len(seen) / max(1, len(observed) or 1)

        if filename_bates is not None and begin.number == filename_bates.number:
            confidence = CONF_CONFIRMED
            notes.append("observed begin stamp matches filename Bates")
        elif coverage >= 0.99 and len(seen) > 1:
            confidence = CONF_CONFIRMED
            notes.append("a Bates stamp was observed on every page")
        elif coverage >= 0.5:
            confidence = CONF_PROBABLE
            notes.append(f"stamps observed on {len(seen)} of {len(observed)} pages")
        else:
            confidence = CONF_POSSIBLE
            notes.append(f"stamps observed on only {len(seen)} of {len(observed)} pages")

        if filename_bates is not None and begin.number != filename_bates.number:
            notes.append(
                f"filename Bates {filename_bates.normalized} differs from observed "
                f"begin {begin.normalized}"
            )
            if confidence == CONF_CONFIRMED:
                confidence = CONF_PROBABLE

        # A multi-page document whose observed span is shorter than its page
        # count is suspicious; report it rather than silently extending.
        if page_count and (end.number - begin.number + 1) < page_count:
            notes.append(
                f"observed span {end.number - begin.number + 1} is smaller than "
                f"page count {page_count}"
            )
        return BatesRange(begin, end, SOURCE_OBSERVED, confidence, notes)

    if filename_bates is not None:
        if page_count and page_count > 1:
            end = parser.make(filename_bates.number + page_count - 1)
            notes.append(
                "end Bates calculated as begin + page count - 1; not observed "
                "on any page"
            )
            return BatesRange(
                filename_bates, end, SOURCE_CALCULATED, CONF_POSSIBLE, notes
            )
        notes.append("Bates taken from filename only; no stamp observed")
        return BatesRange(
            filename_bates, filename_bates, SOURCE_FILENAME, CONF_POSSIBLE, notes
        )

    notes.append("no Bates number found in filename or page text")
    return BatesRange(None, None, SOURCE_NONE, CONF_UNKNOWN, notes)


# ---------------------------------------------------------------------------
# gaps and overlaps
# ---------------------------------------------------------------------------
@dataclass
class BatesGap:
    """A discontinuity between two consecutive Bates ranges."""

    after: int
    before: int
    missing_count: int
    preliminary: bool
    note: str = ""


@dataclass
class BatesOverlap:
    """Two ranges that claim the same Bates numbers."""

    first_label: str
    second_label: str
    overlap_start: int
    overlap_end: int
    note: str = ""


def find_filename_gaps(
    numbers: Iterable[int], *, preliminary: bool = True
) -> List[BatesGap]:
    """Find gaps in a set of Bates numbers taken from filenames.

    These gaps are **preliminary**.  Each PDF in this production may contain
    several Bates-numbered pages, so a numeric jump between two filenames does
    not by itself prove that pages are missing.  The ``preliminary`` flag is
    carried through to the report so the distinction survives.
    """
    unique = sorted({int(n) for n in numbers if n is not None})
    gaps: List[BatesGap] = []
    for previous, current in zip(unique, unique[1:]):
        if current - previous > 1:
            gaps.append(
                BatesGap(
                    after=previous,
                    before=current,
                    missing_count=current - previous - 1,
                    preliminary=preliminary,
                    note=(
                        "Preliminary: based on filenames only. A single PDF may "
                        "contain multiple Bates-numbered pages, so this may not "
                        "be a true production gap."
                        if preliminary
                        else "Based on observed page ranges."
                    ),
                )
            )
    return gaps


def find_range_gaps_and_overlaps(
    ranges: Sequence[Tuple[str, Optional[int], Optional[int]]]
) -> Tuple[List[BatesGap], List[BatesOverlap]]:
    """Find gaps and overlaps across document-level ``(label, begin, end)`` ranges.

    Ranges with a missing begin or end are ignored (and are reported elsewhere
    as unknown-Bates documents).  The scan is linear after sorting, so it does
    not perform an O(n^2) comparison.
    """
    usable = sorted(
        ((label, int(begin), int(end)) for label, begin, end in ranges
         if begin is not None and end is not None),
        key=lambda item: (item[1], item[2]),
    )
    gaps: List[BatesGap] = []
    overlaps: List[BatesOverlap] = []
    if not usable:
        return gaps, overlaps

    _, _, high_water = usable[0]
    high_label = usable[0][0]
    for label, begin, end in usable[1:]:
        if begin > high_water + 1:
            gaps.append(
                BatesGap(
                    after=high_water,
                    before=begin,
                    missing_count=begin - high_water - 1,
                    preliminary=False,
                    note="Derived from begin/end Bates ranges across documents.",
                )
            )
        elif begin <= high_water:
            overlaps.append(
                BatesOverlap(
                    first_label=high_label,
                    second_label=label,
                    overlap_start=begin,
                    overlap_end=min(end, high_water),
                    note="Two documents claim the same Bates numbers.",
                )
            )
        if end > high_water:
            high_water = end
            high_label = label
    return gaps, overlaps


def summarize_numbers(numbers: Sequence[int]) -> Dict[str, Optional[int]]:
    """Return min/max/count/distinct statistics for a set of Bates numbers."""
    values = sorted(int(n) for n in numbers if n is not None)
    if not values:
        return {"count": 0, "distinct": 0, "min": None, "max": None, "span": None}
    return {
        "count": len(values),
        "distinct": len(set(values)),
        "min": values[0],
        "max": values[-1],
        "span": values[-1] - values[0] + 1,
    }
