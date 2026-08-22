"""Platforms are distribution, not strategy.

The order is always brand -> audience -> psychological objective -> story ->
creative -> platform -> distribution -> measurement. This module is only the
sixth step: how one story gets adapted, never copied, per surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .audiences import Audience


class Platform(str, Enum):
    INSTAGRAM_REEL = "instagram_reel"
    INSTAGRAM_FEED = "instagram_feed"
    INSTAGRAM_STORY = "instagram_story"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    YOUTUBE = "youtube"
    LINKEDIN = "linkedin"

    @property
    def spec(self) -> "PlatformSpec":
        return PLATFORMS[self]

    @property
    def label(self) -> str:
        return PLATFORMS[self].name


@dataclass(frozen=True)
class PlatformSpec:
    platform: Platform
    name: str
    surface: str  # short_video | feed | story | long_video | professional
    aspect: str
    duration_s: tuple[int, int] | None
    caption_chars: tuple[int, int]
    hashtags: tuple[int, int]
    primary_audiences: tuple[Audience, ...]
    voice: str
    cta_style: str
    paid_capable: bool
    notes: str


PLATFORMS: dict[Platform, PlatformSpec] = {
    Platform.INSTAGRAM_REEL: PlatformSpec(
        platform=Platform.INSTAGRAM_REEL,
        name="Instagram Reels",
        surface="short_video",
        aspect="9:16",
        duration_s=(12, 35),
        caption_chars=(90, 300),
        hashtags=(3, 6),
        primary_audiences=(Audience.GRADE_8, Audience.GRADE_6_7, Audience.PROSPECTIVE_PARENT),
        voice="Visual storytelling. Identity, belonging, aspiration. Let the room talk.",
        cta_style="Soft, in-caption. Never on-screen in the first three seconds.",
        paid_capable=True,
        notes="Text hook on frame one. Captions burned in -- most viewing is silent.",
    ),
    Platform.INSTAGRAM_FEED: PlatformSpec(
        platform=Platform.INSTAGRAM_FEED,
        name="Instagram Feed",
        surface="feed",
        aspect="4:5",
        duration_s=None,
        caption_chars=(120, 500),
        hashtags=(3, 6),
        primary_audiences=(Audience.CURRENT_PARENT, Audience.GRADE_8, Audience.ALUMNI),
        voice="Considered. One strong image beats a carousel of adequate ones.",
        cta_style="In-caption, one line, at the end.",
        paid_capable=True,
        notes="First line is the hook -- it is all that shows before 'more'.",
    ),
    Platform.INSTAGRAM_STORY: PlatformSpec(
        platform=Platform.INSTAGRAM_STORY,
        name="Instagram Stories",
        surface="story",
        aspect="9:16",
        duration_s=(5, 15),
        caption_chars=(0, 80),
        hashtags=(0, 1),
        primary_audiences=(Audience.CURRENT_PARENT, Audience.GRADE_8),
        voice="Immediate and unpolished. This is the same-day surface.",
        cta_style="Link sticker or poll. Interaction over instruction.",
        paid_capable=False,
        notes="Where today's raw footage goes while it is still today.",
    ),
    Platform.FACEBOOK: PlatformSpec(
        platform=Platform.FACEBOOK,
        name="Facebook",
        surface="feed",
        aspect="4:5 or 1:1",
        duration_s=(20, 75),
        caption_chars=(200, 900),
        hashtags=(0, 2),
        primary_audiences=(Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT,
                           Audience.ALUMNI, Audience.DONOR),
        voice="Parents, alumni and community. More context is welcome here.",
        cta_style="Explicit. Parents will click a plain link.",
        paid_capable=True,
        notes="The parent-trust surface. Longest useful copy of any platform.",
    ),
    Platform.TIKTOK: PlatformSpec(
        platform=Platform.TIKTOK,
        name="TikTok",
        surface="short_video",
        aspect="9:16",
        duration_s=(10, 30),
        caption_chars=(40, 150),
        hashtags=(2, 5),
        primary_audiences=(Audience.GRADE_6_7, Audience.GRADE_8),
        voice=(
            "Authentic, immediate, student-first. Students narrate. Administrators "
            "do not imitate teenage slang -- it reads as costume."
        ),
        cta_style="None, or a single low-pressure line.",
        paid_capable=True,
        notes="Native imperfection outperforms polish. Shoot it, cut it, post it.",
    ),
    Platform.YOUTUBE_SHORTS: PlatformSpec(
        platform=Platform.YOUTUBE_SHORTS,
        name="YouTube Shorts",
        surface="short_video",
        aspect="9:16",
        duration_s=(15, 45),
        caption_chars=(40, 120),
        hashtags=(1, 3),
        primary_audiences=(Audience.GRADE_8, Audience.PROSPECTIVE_PARENT),
        voice="Same cut as the Reel, titled for search.",
        cta_style="In title or description.",
        paid_capable=False,
        notes="Longest useful life of the short surfaces. Title for what a parent types.",
    ),
    Platform.YOUTUBE: PlatformSpec(
        platform=Platform.YOUTUBE,
        name="YouTube",
        surface="long_video",
        aspect="16:9",
        duration_s=(90, 480),
        caption_chars=(300, 1200),
        hashtags=(0, 3),
        primary_audiences=(Audience.PROSPECTIVE_PARENT, Audience.ALUMNI, Audience.DONOR),
        voice="The full story: a student, an alum, a department, a tradition.",
        cta_style="Description link plus a spoken line at the end.",
        paid_capable=True,
        notes="Evergreen. This is the library families find in month two of the search.",
    ),
    Platform.LINKEDIN: PlatformSpec(
        platform=Platform.LINKEDIN,
        name="LinkedIn",
        surface="professional",
        aspect="1:1 or 16:9",
        duration_s=(30, 120),
        caption_chars=(300, 1000),
        hashtags=(0, 3),
        primary_audiences=(Audience.ALUMNI, Audience.DONOR, Audience.PROSPECTIVE_PARENT),
        voice="Institutional accomplishment, outcomes, faculty and leadership.",
        cta_style="Professional and understated.",
        paid_capable=True,
        notes="Where outcomes and faculty credentials belong. Never student-facing.",
    ),
}

SHORT_VIDEO = (Platform.INSTAGRAM_REEL, Platform.TIKTOK, Platform.YOUTUBE_SHORTS)


def platforms_for(audience: Audience) -> tuple[Platform, ...]:
    """Platforms that reach an audience, in that audience's priority order."""
    keys = audience.spec.platforms
    return tuple(Platform(key) for key in keys if key in Platform._value2member_map_)


def caption_fits(platform: Platform, text: str) -> bool:
    low, high = platform.spec.caption_chars
    return low <= len(text) <= high
