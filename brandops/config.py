"""School-specific settings.

Everything a new school year, a new handle or a new landing page would change
lives here. Nothing else in the package hardcodes a URL or a person.

Values left empty render as a visible placeholder rather than a guess -- an
unset link shows up in the draft as `<<set links.visit in brandops/config.py>>`
so it is caught in approval instead of published broken.
"""

from __future__ import annotations

import os

SCHOOL_NAME = "Orchard Lake St. Mary's"
SCHOOL_SHORT = "St. Mary's"

# Fill these in once. Environment variables of the same name (upper-cased,
# prefixed OLSM_) override them, so a staging environment needs no code change.
LINKS: dict[str, str] = {
    "visit": "",        # schedule-a-visit landing page
    "inquiry": "",      # inquiry form
    "shadow": "",       # shadow-day registration
    "apply": "",        # application
    "open_house": "",   # open house registration
    "impact": "",       # donor impact report
    "give": "",         # giving page
}

HANDLES: dict[str, str] = {
    "instagram": "",
    "facebook": "",
    "tiktok": "",
    "youtube": "",
    "linkedin": "",
}

# Brand hashtags, used sparingly. Platform specs cap the count.
BRAND_HASHTAGS: tuple[str, ...] = ("#StMarysPrep",)

# Where the content inbox lives. The QR code on the staff one-pager points here.
CONTENT_INBOX = {
    "provider": "SharePoint / OneDrive",
    "library": "Marketing/Content Inbox",
    "upload_url": "",  # the Microsoft Forms or upload link behind the QR code
}

# Who can approve what. Approval is required for everything; this decides who.
APPROVERS: dict[str, str] = {
    "default": "Director of Marketing",
    "catholic_identity": "Campus Ministry + Director of Marketing",
    "statistics": "Admissions Director",
    "sensitive": "Head of School",
    "donor": "Advancement Director",
}

# Posting windows, local time. Tuned by the weekly report, not by guesswork.
POSTING_WINDOWS: dict[str, tuple[str, ...]] = {
    "instagram_reel": ("15:30", "19:30"),
    "instagram_feed": ("12:00", "19:00"),
    "instagram_story": ("07:30", "12:00", "15:30"),
    "facebook": ("07:30", "12:30", "19:00"),
    "tiktok": ("15:30", "20:00"),
    "youtube_shorts": ("16:00",),
    "youtube": ("18:00",),
    "linkedin": ("08:00", "12:00"),
}

# Planned vs. opportunistic split. A great unplanned moment outranks the calendar.
PLANNED_SHARE = 0.70
OPPORTUNISTIC_SHARE = 0.30

# Volume target per week. Quality gate still applies -- an empty slot is
# better than a mediocre post.
WEEKLY_POST_TARGET = 12


def link(name: str) -> str:
    """Resolve a link, falling back to a loud placeholder rather than a guess."""
    value = os.environ.get(f"OLSM_{name.upper()}_URL") or LINKS.get(name, "")
    return value or f"<<set links.{name} in brandops/config.py>>"


def handle(platform: str) -> str:
    value = os.environ.get(f"OLSM_{platform.upper()}_HANDLE") or HANDLES.get(platform, "")
    return value or f"<<set handles.{platform} in brandops/config.py>>"


def is_placeholder(value: str) -> bool:
    return value.startswith("<<set ")
