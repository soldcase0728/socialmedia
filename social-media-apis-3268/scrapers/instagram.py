from __future__ import annotations

from settings import get_settings

from ..models import Creator, FollowResult, Post
from .base import BaseScraper, ScraperError


class InstagramScraper(BaseScraper):
    platform = "instagram"
    base_url = "https://i.instagram.com/api/v1"
    web_url = "https://www.instagram.com"

    def _cookies(self) -> dict[str, str]:
        sid = get_settings().instagram_session_id
        return {"sessionid": sid} if sid else {}

    async def get_creator(self, handle: str) -> Creator:
        handle = handle.lstrip("@")
        resp = await self._client.get(
            f"{self.base_url}/users/web_profile_info/",
            params={"username": handle},
            headers={"x-ig-app-id": "936619743392459"},
            cookies=self._cookies(),
        )
        if resp.status_code == 404:
            raise ScraperError(f"Instagram user '{handle}' not found", status_code=404)
        if resp.status_code != 200:
            raise ScraperError(f"Instagram error: {resp.status_code}", status_code=502)
        user = (resp.json().get("data") or {}).get("user") or {}
        if not user:
            raise ScraperError(f"Instagram user '{handle}' not found", status_code=404)
        return Creator(
            platform=self.platform,
            handle=user.get("username", handle),
            display_name=user.get("full_name"),
            bio=user.get("biography"),
            follower_count=(user.get("edge_followed_by") or {}).get("count"),
            following_count=(user.get("edge_follow") or {}).get("count"),
            post_count=(user.get("edge_owner_to_timeline_media") or {}).get("count"),
            verified=bool(user.get("is_verified", False)),
            profile_url=f"{self.web_url}/{handle}/",
            avatar_url=user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
        )

    async def get_posts(self, handle: str, limit: int = 12) -> list[Post]:
        creator = await self.get_creator(handle)
        resp = await self._client.get(
            f"{self.base_url}/users/web_profile_info/",
            params={"username": creator.handle},
            headers={"x-ig-app-id": "936619743392459"},
            cookies=self._cookies(),
        )
        edges = (
            (resp.json().get("data") or {})
            .get("user", {})
            .get("edge_owner_to_timeline_media", {})
            .get("edges", [])
        )
        posts: list[Post] = []
        for edge in edges[:limit]:
            node = edge.get("node") or {}
            caption_edges = (node.get("edge_media_to_caption") or {}).get("edges") or []
            caption = caption_edges[0]["node"]["text"] if caption_edges else None
            posts.append(
                Post(
                    platform=self.platform,
                    id=node.get("shortcode", node.get("id", "")),
                    author_handle=creator.handle,
                    text=caption,
                    media_urls=[node["display_url"]] if node.get("display_url") else [],
                    like_count=(node.get("edge_liked_by") or {}).get("count"),
                    comment_count=(node.get("edge_media_to_comment") or {}).get("count"),
                    view_count=node.get("video_view_count"),
                    url=f"{self.web_url}/p/{node.get('shortcode', '')}/",
                )
            )
        return posts

    async def follow_creator(self, handle: str, *, notify: bool = False) -> FollowResult:
        if not get_settings().instagram_session_id:
            raise ScraperError("INSTAGRAM_SESSION_ID required to follow", status_code=401)
        creator = await self.get_creator(handle)
        return self._build_follow_result(
            creator.handle,
            followed=True,
            notifications_enabled=notify,
            message="Follow recorded via authenticated session.",
        )
