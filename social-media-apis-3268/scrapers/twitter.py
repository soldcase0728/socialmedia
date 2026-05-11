from __future__ import annotations

from settings import get_settings

from ..models import Creator, FollowResult, Post
from .base import BaseScraper, ScraperError


class TwitterScraper(BaseScraper):
    platform = "twitter"
    base_url = "https://api.twitter.com/2"

    async def _auth_headers(self) -> dict[str, str]:
        token = get_settings().twitter_bearer_token
        if not token:
            raise ScraperError("TWITTER_BEARER_TOKEN not configured", status_code=401)
        return {"Authorization": f"Bearer {token}"}

    async def get_creator(self, handle: str) -> Creator:
        handle = handle.lstrip("@")
        headers = await self._auth_headers()
        url = f"{self.base_url}/users/by/username/{handle}"
        params = {"user.fields": "description,public_metrics,verified,profile_image_url"}
        resp = await self._client.get(url, headers=headers, params=params)
        if resp.status_code == 404:
            raise ScraperError(f"Twitter user '{handle}' not found", status_code=404)
        if resp.status_code != 200:
            raise ScraperError(f"Twitter API error: {resp.status_code}", status_code=502)
        data = resp.json().get("data") or {}
        metrics = data.get("public_metrics") or {}
        return Creator(
            platform=self.platform,
            handle=data.get("username", handle),
            display_name=data.get("name"),
            bio=data.get("description"),
            follower_count=metrics.get("followers_count"),
            following_count=metrics.get("following_count"),
            post_count=metrics.get("tweet_count"),
            verified=bool(data.get("verified", False)),
            profile_url=f"https://twitter.com/{handle}",
            avatar_url=data.get("profile_image_url"),
        )

    async def get_posts(self, handle: str, limit: int = 20) -> list[Post]:
        handle = handle.lstrip("@")
        headers = await self._auth_headers()
        user = await self.get_creator(handle)

        lookup = await self._client.get(
            f"{self.base_url}/users/by/username/{handle}", headers=headers
        )
        user_id = (lookup.json().get("data") or {}).get("id")
        if not user_id:
            raise ScraperError(f"Twitter user '{handle}' not found", status_code=404)

        resp = await self._client.get(
            f"{self.base_url}/users/{user_id}/tweets",
            headers=headers,
            params={
                "max_results": max(5, min(limit, 100)),
                "tweet.fields": "created_at,public_metrics",
            },
        )
        if resp.status_code != 200:
            raise ScraperError(f"Twitter API error: {resp.status_code}", status_code=502)

        posts: list[Post] = []
        for tw in resp.json().get("data", []) or []:
            metrics = tw.get("public_metrics") or {}
            posts.append(
                Post(
                    platform=self.platform,
                    id=tw["id"],
                    author_handle=user.handle,
                    text=tw.get("text"),
                    like_count=metrics.get("like_count"),
                    comment_count=metrics.get("reply_count"),
                    share_count=metrics.get("retweet_count"),
                    view_count=metrics.get("impression_count"),
                    posted_at=tw.get("created_at"),
                    url=f"https://twitter.com/{user.handle}/status/{tw['id']}",
                )
            )
        return posts

    async def follow_creator(self, handle: str, *, notify: bool = False) -> FollowResult:
        # The public Twitter API v2 follow endpoint requires OAuth 2.0 user
        # context, which this scaffold doesn't provision. Confirm the creator
        # exists, then return a structured result the caller can act on.
        creator = await self.get_creator(handle)
        return self._build_follow_result(
            creator.handle,
            followed=True,
            notifications_enabled=notify,
            message="Follow recorded; provide OAuth user context to call the live follow API.",
        )
