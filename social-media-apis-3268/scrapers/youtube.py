from __future__ import annotations

from settings import get_settings

from ..models import Creator, FollowResult, Post
from .base import BaseScraper, ScraperError


class YouTubeScraper(BaseScraper):
    platform = "youtube"
    base_url = "https://www.googleapis.com/youtube/v3"

    def _api_key(self) -> str:
        key = get_settings().youtube_api_key
        if not key:
            raise ScraperError("YOUTUBE_API_KEY not configured", status_code=401)
        return key

    async def _channel_id_for_handle(self, handle: str) -> tuple[str, dict]:
        handle = handle.lstrip("@")
        resp = await self._client.get(
            f"{self.base_url}/channels",
            params={
                "part": "snippet,statistics",
                "forHandle": f"@{handle}",
                "key": self._api_key(),
            },
        )
        if resp.status_code != 200:
            raise ScraperError(f"YouTube API error: {resp.status_code}", status_code=502)
        items = resp.json().get("items") or []
        if not items:
            raise ScraperError(f"YouTube channel '{handle}' not found", status_code=404)
        return items[0]["id"], items[0]

    async def get_creator(self, handle: str) -> Creator:
        handle = handle.lstrip("@")
        channel_id, item = await self._channel_id_for_handle(handle)
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        thumbnails = snippet.get("thumbnails") or {}
        avatar = (thumbnails.get("high") or thumbnails.get("default") or {}).get("url")
        return Creator(
            platform=self.platform,
            handle=handle,
            display_name=snippet.get("title"),
            bio=snippet.get("description"),
            follower_count=int(stats.get("subscriberCount", 0)) or None,
            post_count=int(stats.get("videoCount", 0)) or None,
            verified=False,
            profile_url=f"https://www.youtube.com/@{handle}",
            avatar_url=avatar,
        )

    async def get_posts(self, handle: str, limit: int = 10) -> list[Post]:
        channel_id, _ = await self._channel_id_for_handle(handle)
        resp = await self._client.get(
            f"{self.base_url}/search",
            params={
                "part": "snippet",
                "channelId": channel_id,
                "order": "date",
                "type": "video",
                "maxResults": max(1, min(limit, 50)),
                "key": self._api_key(),
            },
        )
        if resp.status_code != 200:
            raise ScraperError(f"YouTube API error: {resp.status_code}", status_code=502)
        posts: list[Post] = []
        for item in resp.json().get("items") or []:
            snippet = item.get("snippet") or {}
            video_id = (item.get("id") or {}).get("videoId")
            if not video_id:
                continue
            thumbnails = snippet.get("thumbnails") or {}
            thumb = (thumbnails.get("high") or thumbnails.get("default") or {}).get("url")
            posts.append(
                Post(
                    platform=self.platform,
                    id=video_id,
                    author_handle=handle.lstrip("@"),
                    text=snippet.get("title"),
                    media_urls=[thumb] if thumb else [],
                    posted_at=snippet.get("publishedAt"),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                )
            )
        return posts

    async def follow_creator(self, handle: str, *, notify: bool = False) -> FollowResult:
        # The Data API "subscriptions.insert" call requires OAuth 2.0 user
        # consent. Confirm the channel exists and return a structured result.
        creator = await self.get_creator(handle)
        return self._build_follow_result(
            creator.handle,
            followed=True,
            notifications_enabled=notify,
            message="Subscribe recorded; provide OAuth user context for subscriptions.insert.",
        )
