"""Platform-specific copy.

The same story, adapted per surface -- never the same text pasted five times.
Every draft is linted before it can reach the approval queue: institutional
filler, unverified claims, unset links and adults performing teen slang all
fail the check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence

from . import config
from .audiences import Audience
from .brand import CopyFlag, Pillar, scan_copy
from .hooks import Hook
from .packages import ContentItem
from .platforms import Platform

PILLAR_HASHTAGS: dict[Pillar, tuple[str, ...]] = {
    Pillar.KNOWN: ("#KnownHere",),
    Pillar.CHALLENGED: ("#TheWorkIsReal",),
    Pillar.FORMATION: ("#FormedNotJustPrepared",),
    Pillar.CATHOLIC: ("#CatholicEducation",),
    Pillar.BELONGING: ("#StudentLife",),
    Pillar.OUTCOMES: ("#ClassOf", "#WhereTheyGo"),
}

# An institutional account writing like a fifteen-year-old reads as costume.
ADULT_SLANG_TRAPS: tuple[str, ...] = (
    "rizz", "no cap", "bussin", "slay", "goated", "fr fr", "it's giving",
    "cheugy", "sigma", "based", "yeet", "lowkey obsessed",
)

CTA_BY_AUDIENCE: dict[Audience, str] = {
    Audience.PROSPECTIVE_PARENT: "Come see a normal Tuesday here: {visit}",
    Audience.GRADE_8: "Spend a day with us -- shadow a student: {shadow}",
    Audience.GRADE_6_7: "",  # familiarity first; asking this early breaks it
    Audience.CURRENT_PARENT: "Know a family who is deciding? Send them this.",
    Audience.ALUMNI: "Come back and see it: {visit}",
    Audience.DONOR: "See where this year's gifts went: {impact}",
}


@dataclass
class CopyDraft:
    platform: Platform | None
    audience: Audience
    opening: str
    body: str
    cta: str
    hashtags: tuple[str, ...]
    alt_text: str
    title: str = ""
    flags: tuple[CopyFlag, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        parts = [self.opening, self.body, self.cta]
        caption = "\n\n".join(p.strip() for p in parts if p and p.strip())
        if self.hashtags:
            caption = f"{caption}\n\n{' '.join(self.hashtags)}"
        return caption

    @property
    def clean(self) -> bool:
        return not self.flags and not self.warnings

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform.value if self.platform else None,
            "audience": self.audience.value,
            "title": self.title,
            "text": self.text,
            "alt_text": self.alt_text,
            "flags": [str(f) for f in self.flags],
            "warnings": list(self.warnings),
        }


def _cta(audience: Audience) -> str:
    template = CTA_BY_AUDIENCE.get(audience, "")
    if not template:
        return ""
    return template.format(
        visit=config.link("visit"),
        shadow=config.link("shadow"),
        inquiry=config.link("inquiry"),
        impact=config.link("impact"),
        apply=config.link("apply"),
    )


def _evidence_sentence(evidence: Sequence[str]) -> str:
    facts = [e.strip().rstrip(".") for e in evidence if e and e.strip()]
    if not facts:
        return ""
    if len(facts) == 1:
        return facts[0] + "."
    return "; ".join(facts[:-1]) + f"; and {facts[-1]}."


def _hashtags(platform: Platform | None, pillar: Pillar) -> tuple[str, ...]:
    if platform is None:
        return ()
    low, high = platform.spec.hashtags
    if high == 0:
        return ()
    tags = list(config.BRAND_HASHTAGS) + list(PILLAR_HASHTAGS.get(pillar, ()))
    return tuple(tags[:high])


def _lint(draft_text: str, platform: Platform | None) -> tuple[tuple[CopyFlag, ...], tuple[str, ...]]:
    flags = tuple(scan_copy(draft_text))
    warnings: list[str] = []
    lowered = draft_text.lower()

    for slang in ADULT_SLANG_TRAPS:
        if slang in lowered:
            warnings.append(
                f"'{slang}' -- the school account should not perform teen slang; "
                "put the words in a student's mouth or cut them"
            )
    if "<<set " in draft_text:
        warnings.append("unset link or handle in copy -- fill it in brandops/config.py")
    if re.search(r"\b\d{2,}%|\$\d", draft_text) :
        warnings.append("contains a statistic -- verify the source before approval")
    if platform is not None:
        low, high = platform.spec.caption_chars
        length = len(draft_text)
        if length > high:
            warnings.append(f"caption is {length} chars; {platform.spec.name} wants under {high}")
        elif length < low:
            warnings.append(f"caption is {length} chars; {platform.spec.name} wants at least {low}")
    return flags, tuple(warnings)


def write_copy(
    item: ContentItem,
    *,
    story: str,
    pillar: Pillar,
    hook: Hook | None = None,
    evidence: Sequence[str] = (),
    quote: str = "",
    quote_attribution: str = "",
) -> CopyDraft:
    """Draft copy for one package item, adapted to its platform."""
    audience = item.audience
    platform = item.platform
    story_line = story.strip().rstrip(".")
    evidence_line = _evidence_sentence(evidence)
    quote_line = f'"{quote.strip()}" -- {quote_attribution}'.rstrip(" -") if quote else ""
    hook_line = hook.text if hook else story_line + "."
    cta = _cta(audience)
    title = ""

    if platform is Platform.FACEBOOK:
        opening = hook_line
        body = " ".join(p for p in [story_line + ".", evidence_line, quote_line] if p)
    elif platform is Platform.INSTAGRAM_FEED:
        opening = hook_line
        body = " ".join(p for p in [evidence_line or story_line + ".", quote_line] if p)
    elif platform is Platform.INSTAGRAM_REEL:
        opening = hook_line
        body = evidence_line or story_line + "."
    elif platform is Platform.TIKTOK:
        opening = hook_line
        # A student's own words first; the fact second; never a restatement of
        # the hook, which is what the story line would be here.
        body = quote_line or evidence_line
        cta = ""  # students are not being sold to here
    elif platform is Platform.INSTAGRAM_STORY:
        opening = hook_line
        body = ""
        cta = cta.split(":")[0] if cta else ""
    elif platform is Platform.YOUTUBE_SHORTS:
        title = f"{story_line} | {config.SCHOOL_SHORT}"
        opening = hook_line
        body = evidence_line
    elif platform is Platform.YOUTUBE:
        title = f"{story_line} -- {config.SCHOOL_NAME}"
        opening = hook_line
        body = " ".join(p for p in [story_line + ".", evidence_line, quote_line] if p)
    elif platform is Platform.LINKEDIN:
        opening = evidence_line or hook_line
        body = " ".join(p for p in [story_line + ".", quote_line] if p)
    else:  # internal destinations -- a working note, not a caption
        opening = hook_line
        body = " ".join(p for p in [story_line + ".", evidence_line, quote_line] if p)
        cta = ""

    hashtags = _hashtags(platform, pillar)
    alt_text = (
        f"{story_line}. {evidence_line}".strip()
        or f"Students at {config.SCHOOL_SHORT} during {item.fmt}."
    )
    draft = CopyDraft(
        platform=platform,
        audience=audience,
        opening=opening,
        body=body,
        cta=cta,
        hashtags=hashtags,
        alt_text=alt_text[:280],
        title=title,
    )
    flags, warnings = _lint(draft.text, platform)
    draft.flags = flags
    draft.warnings = warnings
    return draft


def write_package_copy(
    items: Sequence[ContentItem],
    *,
    story: str,
    pillar: Pillar,
    hook: Hook | None = None,
    evidence: Sequence[str] = (),
    quote: str = "",
    quote_attribution: str = "",
) -> list[CopyDraft]:
    return [
        write_copy(
            item,
            story=story,
            pillar=pillar,
            hook=hook,
            evidence=evidence,
            quote=quote,
            quote_attribution=quote_attribution,
        )
        for item in items
    ]
