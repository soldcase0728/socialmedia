"""Tests for duplicate hashing, normalisation and near-duplicate grouping."""

from __future__ import annotations

import hashlib

import pytest

from src.duplicates import (
    KIND_NEAR,
    REL_SAME_TEXT_DIFFERENT_RENDERING,
    TextNormalizer,
    band_keys,
    build_fingerprint,
    group_exact_text,
    group_near_duplicates,
    hamming_distance,
    shingles,
    simhash,
)
from src.inventory import sha256_file


class TestFileHashing:
    """SHA-256 of file bytes."""

    def test_matches_hashlib(self, tmp_path):
        path = tmp_path / "sample.bin"
        payload = b"wilson rode production sample bytes"
        path.write_bytes(payload)
        assert sha256_file(path) == hashlib.sha256(payload).hexdigest()

    def test_identical_content_hashes_identically(self, tmp_path):
        a, b = tmp_path / "a.bin", tmp_path / "b.bin"
        a.write_bytes(b"same")
        b.write_bytes(b"same")
        assert sha256_file(a) == sha256_file(b)

    def test_one_byte_difference_changes_the_hash(self, tmp_path):
        a, b = tmp_path / "a.bin", tmp_path / "b.bin"
        a.write_bytes(b"same")
        b.write_bytes(b"samf")
        assert sha256_file(a) != sha256_file(b)

    def test_chunking_does_not_change_the_result(self, tmp_path):
        path = tmp_path / "big.bin"
        path.write_bytes(b"x" * (1024 * 64))
        assert sha256_file(path, chunk_bytes=17) == sha256_file(path, chunk_bytes=8192)


class TestNormalization:
    """Text normalisation before hashing."""

    def test_strips_bates_stamps(self):
        normalizer = TextNormalizer([r"WILSONRODE\s*\d{4,10}"])
        assert "wilsonrode" not in normalizer.normalize("Body text WILSONRODE000123")

    def test_collapses_case_and_whitespace(self):
        normalizer = TextNormalizer()
        assert normalizer.normalize("Hello   WORLD\n\n") == "hello world"

    def test_same_text_different_stamps_hashes_the_same(self):
        normalizer = TextNormalizer([r"WILSONRODE\s*\d{4,10}"])
        left = normalizer.digest("The agreement is binding. WILSONRODE000001")
        right = normalizer.digest("The agreement is binding. WILSONRODE000999")
        assert left == right

    def test_empty_text_has_no_digest(self):
        assert TextNormalizer().digest("   ") is None


class TestSimHash:
    """SimHash fingerprints and LSH banding."""

    def test_identical_text_has_identical_fingerprints(self):
        text = "the parties agree that commission shall continue " * 10
        assert simhash(text) == simhash(text)

    def test_similar_text_is_close(self):
        base = "the parties agree that residual commission shall continue " * 10
        variant = base + " one additional trailing clause here"
        assert hamming_distance(simhash(base), simhash(variant)) <= 6

    def test_different_text_is_far(self):
        left = simhash("statute of frauds analysis and one year provision " * 10)
        right = simhash("invoice for professional services rendered monthly " * 10)
        assert hamming_distance(left, right) > 8

    def test_empty_text_fingerprints_to_zero(self):
        assert simhash("") == 0

    def test_shingles_are_overlapping(self):
        assert shingles(["a", "b", "c", "d"], 2) == ["a b", "b c", "c d"]

    def test_short_input_returns_tokens(self):
        assert shingles(["a", "b"], 4) == ["a", "b"]

    def test_band_keys_count_matches_configuration(self):
        assert len(band_keys(12345, bits=64, bands=8)) == 8

    def test_identical_fingerprints_share_all_bands(self):
        assert band_keys(999, bits=64, bands=8) == band_keys(999, bits=64, bands=8)


class TestGrouping:
    """Group formation across the three duplicate passes."""

    @staticmethod
    def _fingerprints(texts):
        normalizer = TextNormalizer()
        return [build_fingerprint(i, text, normalizer)
                for i, text in enumerate(texts, start=1)]

    def test_exact_text_groups_identical_documents(self):
        body = "the parties agree that residual commission continues " * 20
        groups = group_exact_text(self._fingerprints([body, body, "unrelated " * 60]))
        assert len(groups) == 1
        assert sorted(groups[0].file_ids) == [1, 2]
        assert groups[0].relation == REL_SAME_TEXT_DIFFERENT_RENDERING

    def test_exact_text_ignores_short_documents(self):
        groups = group_exact_text(self._fingerprints(["short", "short"]),
                                  min_chars=200)
        assert groups == []

    def test_near_duplicates_are_grouped(self):
        base = "the commission agreement provides for residual payments " * 25
        variant = base + " with one additional sentence appended at the end."
        groups = group_near_duplicates(
            self._fingerprints([base, variant, "wholly different content " * 40]),
            max_distance=8, confirm_similarity=80,
        )
        assert len(groups) == 1
        assert sorted(groups[0].file_ids) == [1, 2]
        assert groups[0].kind == KIND_NEAR

    def test_unrelated_documents_are_not_grouped(self):
        groups = group_near_duplicates(
            self._fingerprints([
                "statute of frauds analysis regarding the one year provision " * 25,
                "invoice for professional accounting services rendered " * 25,
            ]),
            max_distance=3, confirm_similarity=88,
        )
        assert groups == []

    def test_excluded_pairs_are_skipped(self):
        base = "the commission agreement provides for residual payments " * 25
        groups = group_near_duplicates(
            self._fingerprints([base, base]),
            max_distance=8, confirm_similarity=80,
            exclude_pairs={(1, 2)},
        )
        assert groups == []

    def test_single_document_yields_no_groups(self):
        assert group_near_duplicates(self._fingerprints(["only one " * 60])) == []

    def test_grouping_is_not_quadratic(self):
        """A large corpus of unrelated documents must not be all-pairs compared."""
        texts = [f"unique document number {i} with distinct content " * 25
                 for i in range(300)]
        groups = group_near_duplicates(self._fingerprints(texts),
                                       max_distance=3, confirm_similarity=95)
        assert groups == []
