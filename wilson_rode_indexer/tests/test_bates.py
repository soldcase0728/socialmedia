"""Tests for Bates parsing, ranges, gaps and overlaps."""

from __future__ import annotations

import pytest

from src.bates import (
    CONF_CONFIRMED,
    CONF_POSSIBLE,
    CONF_PROBABLE,
    CONF_UNKNOWN,
    BatesParser,
    SOURCE_CALCULATED,
    SOURCE_FILENAME,
    SOURCE_NONE,
    SOURCE_OBSERVED,
    build_range,
    find_filename_gaps,
    find_range_gaps_and_overlaps,
    summarize_numbers,
)


@pytest.fixture
def parser() -> BatesParser:
    """A parser with the production's default settings."""
    return BatesParser()


class TestFilenameParsing:
    """Bates numbers parsed from filenames."""

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("WILSONRODE000001-null.pdf", 1),
            ("WILSONRODE000012-null.pdf", 12),
            ("WILSONRODE063725-null.pdf", 63725),
            ("wilsonrode000042-null.pdf", 42),
            ("prefix_WILSONRODE001234_suffix.pdf", 1234),
        ],
    )
    def test_parses_expected_number(self, parser, filename, expected):
        result = parser.parse_filename(filename)
        assert result is not None
        assert result.number == expected

    @pytest.mark.parametrize(
        "filename", ["scan_0001.pdf", "", "notes.docx", "WILSONRODE-null.pdf"]
    )
    def test_returns_none_when_absent(self, parser, filename):
        assert parser.parse_filename(filename) is None

    def test_normalizes_with_configured_padding(self, parser):
        assert parser.parse_filename("WILSONRODE000007-null.pdf").normalized == (
            "WILSONRODE000007"
        )

    def test_preserves_wider_padding(self, parser):
        """A number wider than the configured pad width is not truncated."""
        result = parser.parse_filename("WILSONRODE12345678-null.pdf")
        assert result.number == 12345678
        assert result.normalized == "WILSONRODE12345678"

    @pytest.mark.parametrize(
        "filename,compliant",
        [
            ("WILSONRODE000001-null.pdf", True),
            ("WILSONRODE063725-null.pdf", True),
            ("WILSONRODE00001-null.pdf", False),
            ("WILSONRODE000001.pdf", False),
            ("scan_0001.pdf", False),
        ],
    )
    def test_pattern_compliance(self, parser, filename, compliant):
        assert parser.is_filename_compliant(filename) is compliant


class TestPageParsing:
    """Bates stamps read from page text."""

    def test_finds_stamp_in_text(self, parser):
        found = parser.find_in_text("Some body text\n\nWILSONRODE000123")
        assert [b.number for b in found] == [123]

    def test_tolerates_separator_characters(self, parser):
        assert parser.find_in_text("WILSONRODE 000123")[0].number == 123
        assert parser.find_in_text("WILSONRODE-000123")[0].number == 123

    def test_footer_takes_precedence_over_body(self, parser):
        """A stamp in the footer wins over a number quoted in the body."""
        stamp = parser.find_on_page(
            page_text="Refers to WILSONRODE000999 in the body.\nWILSONRODE000123",
            footer_text="WILSONRODE000123",
        )
        assert stamp.number == 123

    def test_returns_none_when_no_stamp(self, parser):
        assert parser.find_on_page("no stamp here", "") is None


class TestBuildRange:
    """Range assembly and its provenance."""

    def test_observed_matching_filename_is_confirmed(self, parser):
        result = build_range(
            parser,
            filename_bates=parser.make(10),
            observed=[parser.make(10), parser.make(11)],
            page_count=2,
        )
        assert result.begin_num == 10
        assert result.end_num == 11
        assert result.source == SOURCE_OBSERVED
        assert result.confidence == CONF_CONFIRMED

    def test_observed_without_filename_is_confirmed_when_complete(self, parser):
        result = build_range(
            parser, filename_bates=None,
            observed=[parser.make(5), parser.make(6)], page_count=2,
        )
        assert result.confidence == CONF_CONFIRMED
        assert result.source == SOURCE_OBSERVED

    def test_partial_observation_is_probable(self, parser):
        result = build_range(
            parser, filename_bates=None,
            observed=[parser.make(5), None, None], page_count=3,
        )
        assert result.confidence == CONF_POSSIBLE

    def test_filename_only_multipage_is_calculated(self, parser):
        result = build_range(
            parser, filename_bates=parser.make(100), observed=[None, None, None],
            page_count=3,
        )
        assert result.source == SOURCE_CALCULATED
        assert result.confidence == CONF_POSSIBLE
        assert result.begin_num == 100
        assert result.end_num == 102
        assert any("calculated" in note for note in result.notes)

    def test_filename_only_single_page(self, parser):
        result = build_range(
            parser, filename_bates=parser.make(7), observed=[None], page_count=1
        )
        assert result.source == SOURCE_FILENAME
        assert result.begin_num == result.end_num == 7

    def test_no_evidence_is_unknown(self, parser):
        result = build_range(parser, filename_bates=None, observed=[None],
                             page_count=1)
        assert result.source == SOURCE_NONE
        assert result.confidence == CONF_UNKNOWN
        assert result.begin_str is None

    def test_filename_observed_mismatch_is_noted_and_downgraded(self, parser):
        result = build_range(
            parser, filename_bates=parser.make(10),
            observed=[parser.make(50), parser.make(51)], page_count=2,
        )
        assert result.confidence == CONF_PROBABLE
        assert any("differs from observed" in note for note in result.notes)

    def test_span_shorter_than_page_count_is_noted(self, parser):
        result = build_range(
            parser, filename_bates=parser.make(1),
            observed=[parser.make(1), parser.make(1), parser.make(1)], page_count=3,
        )
        assert any("smaller than page count" in note for note in result.notes)


class TestGaps:
    """Gap and overlap detection."""

    def test_filename_gaps_are_marked_preliminary(self):
        gaps = find_filename_gaps([1, 2, 5, 6, 10])
        assert [(g.after, g.before, g.missing_count) for g in gaps] == [
            (2, 5, 2), (6, 10, 3)
        ]
        assert all(gap.preliminary for gap in gaps)
        assert all("Preliminary" in gap.note for gap in gaps)

    def test_contiguous_numbers_have_no_gaps(self):
        assert find_filename_gaps([1, 2, 3, 4]) == []

    def test_duplicates_do_not_create_gaps(self):
        assert find_filename_gaps([1, 1, 2, 2, 3]) == []

    def test_range_gaps_are_not_preliminary(self):
        gaps, overlaps = find_range_gaps_and_overlaps(
            [("a", 1, 5), ("b", 10, 12)]
        )
        assert len(gaps) == 1
        assert gaps[0].missing_count == 4
        assert gaps[0].preliminary is False
        assert overlaps == []

    def test_detects_overlaps(self):
        gaps, overlaps = find_range_gaps_and_overlaps(
            [("a", 1, 10), ("b", 5, 15)]
        )
        assert gaps == []
        assert len(overlaps) == 1
        assert overlaps[0].overlap_start == 5
        assert overlaps[0].overlap_end == 10

    def test_adjacent_ranges_are_neither_gap_nor_overlap(self):
        gaps, overlaps = find_range_gaps_and_overlaps([("a", 1, 5), ("b", 6, 9)])
        assert gaps == [] and overlaps == []

    def test_ranges_with_missing_bounds_are_ignored(self):
        gaps, overlaps = find_range_gaps_and_overlaps(
            [("a", None, None), ("b", 1, 3), ("c", 9, 11)]
        )
        assert len(gaps) == 1

    def test_summarize_numbers(self):
        assert summarize_numbers([5, 1, 3, 3]) == {
            "count": 4, "distinct": 3, "min": 1, "max": 5, "span": 5
        }

    def test_summarize_empty(self):
        summary = summarize_numbers([])
        assert summary["count"] == 0 and summary["min"] is None
