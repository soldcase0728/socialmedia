from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "social-media-apis-3268"
    debug: bool = False
    request_timeout_seconds: float = 30.0
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    twitter_bearer_token: str | None = Field(default=None, alias="TWITTER_BEARER_TOKEN")
    instagram_session_id: str | None = Field(default=None, alias="INSTAGRAM_SESSION_ID")
    tiktok_session_id: str | None = Field(default=None, alias="TIKTOK_SESSION_ID")
    youtube_api_key: str | None = Field(default=None, alias="YOUTUBE_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
