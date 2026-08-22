"""One event is not one post. It is a content package.

Given a triaged asset (or a group of them from the same event), this module
enumerates every reasonable output and the production instructions for each --
so a single classroom visit leaves as a Reel, a TikTok, a parent post, a story,
a still, a short, two quote cards, a website image and an ad test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .assets import Asset, AssetKind
from .audiences import Audience
from .brand import Pillar
from .platforms import Platform
from .triage import TriageResult

# Non-social destinations. These are where the long-term value accumulates.
INTERNAL_DESTINATIONS: dict[str, str] = {
    "website_photo": "Website / viewbook image library",
    "admissions_ad": "Paid admissions creative test",
    "evergreen_library": "Evergreen asset library, tagged by pillar",
    "email_newsletter": "Parent or prospect email",
    "brand_memory": "Brand memory: hook, quote or story worth reusing",
}

POLISH_FAST = "fast"        # everyday storytelling: authenticity stays visible
POLISH_CAMPAIGN = "campaign"  # major brand campaigns only


@dataclass
class ContentItem:
    """One deliverable inside a package."""

    key: str
    platform: Platform | None
    destination: str
    fmt: str
    audience: Audience
    purpose: str
    duration_s: int | None
    production: tuple[str, ...]
    source_assets: tuple[str, ...]
    paid: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "platform": self.platform.value if self.platform else None,
            "destination": self.destination,
            "format": self.fmt,
            "audience": self.audience.value,
            "purpose": self.purpose,
            "duration_s": self.duration_s,
            "production": list(self.production),
            "source_assets": list(self.source_assets),
            "paid": self.paid,
        }


@dataclass
class ContentPackage:
    event: str
    pillar: Pillar
    items: list[ContentItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def platforms(self) -> list[Platform]:
        return [i.platform for i in self.items if i.platform]

    def for_audience(self, audience: Audience) -> list[ContentItem]:
        return [i for i in self.items if i.audience is audience]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "pillar": self.pillar.value,
            "items": [i.to_dict() for i in self.items],
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# Production instructions
# ---------------------------------------------------------------------------

VIDEO_STEPS_FAST: tuple[str, ...] = (
    "pull the three strongest clips; cut everything before the action starts",
    "trim dead air and false starts -- no clip opens on someone walking into frame",
    "auto-transcribe, then pull the single best student or teacher sentence",
    "burn in captions (most of this is watched silent)",
    "clean the audio: reduce room noise, level the voice, drop background music under speech",
    "hold framing steady; crop to 9:16 around the subject rather than re-shooting",
    "on-screen hook text over the first frame, gone by 2.5s",
)

VIDEO_STEPS_CAMPAIGN: tuple[str, ...] = VIDEO_STEPS_FAST + (
    "color match across clips",
    "score it, and mix the music under the voice, never over it",
    "add B-roll to cover every cut where a face changes position",
    "produce 15s, 30s and 45s versions from the same timeline",
)

PHOTO_STEPS: tuple[str, ...] = (
    "pick one frame -- resist the carousel unless the second image adds a fact",
    "straighten, crop to 4:5, lift shadows on faces",
    "no heavy filters; the room should look like the room",
    "write alt text describing what is actually happening",
)

STORY_STEPS: tuple[str, ...] = (
    "post the raw vertical clip same-day, minimal editing",
    "one line of text, large, top third",
    "add the link or poll sticker",
)


def _video_steps(polish: str) -> tuple[str, ...]:
    return VIDEO_STEPS_CAMPAIGN if polish == POLISH_CAMPAIGN else VIDEO_STEPS_FAST


def build_package(
    result: TriageResult,
    assets: Sequence[Asset],
    *,
    polish: str = POLISH_FAST,
) -> ContentPackage:
    """Enumerate everything that can reasonably be made from one event."""
    asset_ids = tuple(a.asset_id for a in assets)
    has_video = any(a.kind is AssetKind.VIDEO for a in assets)
    has_photo = any(a.kind is AssetKind.PHOTO for a in assets)
    event = assets[0].event if assets else result.asset_id
    pillar = result.primary_pillar
    package = ContentPackage(event=event, pillar=pillar)

    student_audience = next(
        (a for a in result.audiences if a in (Audience.GRADE_8, Audience.GRADE_6_7)),
        Audience.GRADE_8,
    )
    parent_audience = next(
        (a for a in result.audiences if a in (Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT)),
        Audience.PROSPECTIVE_PARENT,
    )

    if has_video:
        package.items.append(ContentItem(
            key="reel",
            platform=Platform.INSTAGRAM_REEL,
            destination="Instagram Reels",
            fmt="vertical video",
            audience=student_audience,
            purpose="Belonging and aspiration -- put the viewer inside the room.",
            duration_s=25,
            production=_video_steps(polish),
            source_assets=asset_ids,
        ))
        package.items.append(ContentItem(
            key="tiktok",
            platform=Platform.TIKTOK,
            destination="TikTok",
            fmt="vertical video",
            audience=student_audience,
            purpose="Familiarity with 6th-8th graders before a decision exists.",
            duration_s=18,
            production=_video_steps(POLISH_FAST) + (
                "keep it rougher than the Reel -- polish reads as advertising here",
                "student voice narrates; no adult voiceover",
            ),
            source_assets=asset_ids,
        ))
        package.items.append(ContentItem(
            key="youtube_short",
            platform=Platform.YOUTUBE_SHORTS,
            destination="YouTube Shorts",
            fmt="vertical video",
            audience=Audience.PROSPECTIVE_PARENT,
            purpose="Search-discoverable version with a long useful life.",
            duration_s=35,
            production=_video_steps(polish) + (
                "title it the way a parent would search it, not the way we name events",
            ),
            source_assets=asset_ids,
        ))
        package.items.append(ContentItem(
            key="story_clip",
            platform=Platform.INSTAGRAM_STORY,
            destination="Instagram Stories",
            fmt="story",
            audience=Audience.CURRENT_PARENT,
            purpose="Same-day proof of life for families already here.",
            duration_s=10,
            production=STORY_STEPS,
            source_assets=asset_ids,
        ))

    if has_photo or has_video:
        package.items.append(ContentItem(
            key="parent_post",
            platform=Platform.FACEBOOK,
            destination="Facebook",
            fmt="photo or short video with context",
            audience=parent_audience,
            purpose="The trust surface: more context, more evidence, plainly said.",
            duration_s=None,
            production=(PHOTO_STEPS if has_photo else _video_steps(polish)) + (
                "the caption carries the evidence -- name the course, the teacher, the number",
            ),
            source_assets=asset_ids,
        ))
        package.items.append(ContentItem(
            key="feed_still",
            platform=Platform.INSTAGRAM_FEED,
            destination="Instagram Feed",
            fmt="still photo" if has_photo else "still frame exported from the video",
            audience=Audience.CURRENT_PARENT,
            purpose="One frame that carries the pillar on its own.",
            duration_s=None,
            production=(
                PHOTO_STEPS if has_photo
                else ("export the sharpest frame at full resolution -- check for motion blur "
                      "before committing to it",) + PHOTO_STEPS
            ),
            source_assets=asset_ids,
        ))

    if pillar is Pillar.OUTCOMES:
        package.items.append(ContentItem(
            key="linkedin",
            platform=Platform.LINKEDIN,
            destination="LinkedIn",
            fmt="photo or short video",
            audience=Audience.ALUMNI,
            purpose="Institutional outcome, stated once, with the number in it.",
            duration_s=None,
            production=PHOTO_STEPS + ("lead with the outcome, not the event name",),
            source_assets=asset_ids,
        ))

    # Non-social outputs. These are where compounding value lives.
    package.items.append(ContentItem(
        key="quote_card",
        platform=None,
        destination=INTERNAL_DESTINATIONS["brand_memory"],
        fmt="pull quote",
        audience=parent_audience,
        purpose="Bank the best student or teacher sentence for reuse.",
        duration_s=None,
        production=(
            "lift the strongest sentence from the transcript verbatim",
            "record who said it, when, and in what context",
            "file it in brand memory under this pillar",
        ),
        source_assets=asset_ids,
    ))
    package.items.append(ContentItem(
        key="website_photo",
        platform=None,
        destination=INTERNAL_DESTINATIONS["website_photo"],
        fmt="still photo",
        audience=Audience.PROSPECTIVE_PARENT,
        purpose="Feed the website and viewbook from real days, not stock.",
        duration_s=None,
        production=("export a horizontal crop at full resolution", "tag by pillar and department"),
        source_assets=asset_ids,
    ))
    package.items.append(ContentItem(
        key="evergreen",
        platform=None,
        destination=INTERNAL_DESTINATIONS["evergreen_library"],
        fmt="library entry",
        audience=Audience.PROSPECTIVE_PARENT,
        purpose="Available next January when this pillar runs thin.",
        duration_s=None,
        production=("tag: pillar, audience, department, season", "note what is missing from it"),
        source_assets=asset_ids,
    ))

    if result.paid_candidate:
        package.items.append(ContentItem(
            key="paid_test",
            platform=Platform.INSTAGRAM_REEL,
            destination=INTERNAL_DESTINATIONS["admissions_ad"],
            fmt="paid creative test",
            audience=Audience.PROSPECTIVE_PARENT,
            purpose="Test the organic winner as admissions creative, with its own CTA.",
            duration_s=25,
            production=_video_steps(polish) + (
                "swap the organic ending for a single, explicit call to action",
                "define the audience, the objective and the measurement before it runs",
            ),
            source_assets=asset_ids,
            paid=True,
        ))
        package.notes.append(
            "Paid: this is a creative test, not a boosted post. It needs an audience, "
            "a proposition, proof, a CTA and a measurement plan before it spends."
        )

    if result.needs_more_footage:
        package.notes.append(
            "Package is incomplete until: " + "; ".join(result.needs_more_footage[:3])
        )
    return package


def repurposing_summary(package: ContentPackage) -> str:
    social = [i for i in package.items if i.platform]
    internal = [i for i in package.items if not i.platform]
    return (
        f"{package.event}: {len(package.items)} outputs -- "
        f"{len(social)} published, {len(internal)} banked."
    )
