"""The brand layer: pillars, language discipline, audiences, platforms."""

from __future__ import annotations

import pytest

from brandops.audiences import AUDIENCES, Audience, PILLAR_AUDIENCES, audience_read
from brandops.brand import (
    BANNED_PHRASES,
    PILLARS,
    Pillar,
    classify_pillars,
    proof_prompt,
    scan_copy,
)
from brandops.platforms import PLATFORMS, Platform, caption_fits, platforms_for


def test_pillar_target_shares_sum_to_one():
    assert sum(spec.target_share for spec in PILLARS.values()) == pytest.approx(1.0)


def test_audience_target_shares_sum_to_one():
    assert sum(spec.target_share for spec in AUDIENCES.values()) == pytest.approx(1.0)


def test_every_pillar_has_observable_proof():
    # Proof must be things a camera can see, not adjectives.
    for pillar, spec in PILLARS.items():
        assert spec.proof, f"{pillar} has no proof list"
        assert spec.evidence_test.endswith("?"), f"{pillar}'s evidence test is not a question"


def test_every_pillar_maps_to_audiences():
    assert set(PILLAR_AUDIENCES) == set(Pillar)
    for audiences in PILLAR_AUDIENCES.values():
        assert audiences


def test_scan_copy_flags_institutional_filler():
    flags = scan_copy("Our commitment to academic excellence, preparing tomorrow's leaders.")
    found = {f.found for f in flags}
    assert "academic excellence" in found
    assert any("leaders" in f for f in found)
    assert all(f.remedy for f in flags)


def test_scan_copy_flags_clickbait():
    flags = scan_copy("You won't believe what happened in third period")
    assert any(f.kind == "clickbait" for f in flags)


def test_scan_copy_passes_specific_copy():
    assert scan_copy("Nine juniors ran the titration twice. The first run was off by 0.4 mL.") == []


def test_banned_phrases_all_carry_a_remedy():
    assert all(remedy.strip() for remedy in BANNED_PHRASES.values())


def test_classify_pillars_ranks_by_evidence():
    ranked = classify_pillars("AP Chemistry lab presentation before All-School Mass")
    assert ranked[0][0] is Pillar.CHALLENGED
    assert Pillar.CATHOLIC in [p for p, _ in ranked]


def test_classify_pillars_empty_when_nothing_matches():
    assert classify_pillars("a photograph of a parking lot") == []


def test_proof_prompt_names_the_pillar_and_the_test():
    prompt = proof_prompt(Pillar.KNOWN)
    assert "Known & Safe" in prompt
    assert "?" in prompt


def test_audience_read_distinguishes_parent_student_and_both():
    assert audience_read([Audience.PROSPECTIVE_PARENT]) == "parent"
    assert audience_read([Audience.GRADE_8]) == "student"
    assert audience_read([Audience.GRADE_8, Audience.CURRENT_PARENT]) == "both"
    assert audience_read([Audience.DONOR]) == "community"


def test_platforms_for_audience_are_real_platforms():
    for audience in Audience:
        for platform in platforms_for(audience):
            assert platform in PLATFORMS


def test_grade_6_7_gets_no_cta():
    # Asking a sixth grader to apply breaks the familiarity strategy.
    assert AUDIENCES[Audience.GRADE_6_7].cta_policy.lower().startswith("no cta")


def test_caption_fits_respects_platform_bounds():
    low, high = Platform.INSTAGRAM_STORY.spec.caption_chars
    assert caption_fits(Platform.INSTAGRAM_STORY, "x" * (high - 1))
    assert not caption_fits(Platform.INSTAGRAM_STORY, "x" * (high + 10))


def test_tiktok_voice_warns_against_adult_slang():
    assert "slang" in Platform.TIKTOK.spec.voice.lower()
