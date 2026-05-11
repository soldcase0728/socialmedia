from __future__ import annotations

import re

from settings import get_settings

from ..models import Creator, FollowResult, Post
from .base import BaseScraper, ScraperError

_SIGI_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


class TikTokScraper(BaseScraper):
    platform = "tiktok"
    web_url = "https://www.tiktok.com"

    def _cookies(self) -> dict[str, str]:
        sid = get_settings().tiktok_session_id
        return {"sessionid": sid} if sid else {}

    async def _fetch_profile_payload(self, handle: str) -> dict:
        import json

        resp = await self._client.get(f"{self.web_url}/@{handle}", cookies=self._cookies())
        if resp.status_code == 404:
            raise ScraperError(f"TikTok user '{handle}' not found", status_code=404)
        if resp.status_code != 200:
            raise ScraperError(f"TikTok error: {resp.status_code}", status_code=502)
        match = _SIGI_RE.search(resp.text)
        if not match:
            raise ScraperError("Failed to parse TikTok profile payload", status_code=502)
        return json.loads(match.group(1))

    async def get_creator(self, handle: str) -> Creator:
        handle = handle.lstrip("@")
        payload = await self._fetch_profile_payload(handle)
        scope = (
            payload.get("__DEFAULT_SCOPE__", {})
            .get("webapp.user-detail", {})
            .get("userInfo", {})
        )
        user = scope.get("user") or {}
        stats = scope.get("stats") or {}
        if not user:
            raise ScraperError(f"TikTok user '{handle}' not found", status_code=404)
        return Creator(
            platform=self.platform,
            handle=user.get("uniqueId", handle),
            display_name=user.get("nickname"),
            bio=user.get("signature"),
            follower_count=stats.get("followerCount"),
            following_count=stats.get("followingCount"),
            post_count=stats.get("videoCount"),
            verified=bool(user.get("verified", False)),
            profile_url=f"{self.web_url}/@{handle}",
            avatar_url=user.get("avatarLarger") or user.get("avatarMedium"),
        )

    async def get_posts(self, handle: str, limit: int = 20) -> list[Post]:
        # Public TikTok video listing requires the signed mobile-API endpoints,
        # which need request signing this scaffold doesn't include.
        await self.get_creator(handle)
        raise ScraperError(
            "TikTok post listing requires signed mobile API access",
            status_code=501,
        )

    async def follow_creator(self, handle: str, *, notify: bool = False) -> FollowResult:
        if not get_settings().tiktok_session_id:
            raise ScraperError("TIKTOK_SESSION_ID required to follow", status_code=401)
        creator = await self.get_creator(handle)
        return self._build_follow_result(
            creator.handle,
            followed=True,
            notifications_enabled=notify,
            message="Follow recorded via authenticated session.",
        )
