from fastapi import FastAPI

from settings import get_settings

from .routes import (
    instagram_router,
    tiktok_router,
    twitter_router,
    youtube_router,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Social media scraping APIs with creator follow support.",
        version="0.1.0",
        debug=settings.debug,
    )

    app.include_router(twitter_router)
    app.include_router(instagram_router)
    app.include_router(tiktok_router)
    app.include_router(youtube_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("social_media_apis_3268.main:app", host="0.0.0.0", port=8000, reload=True)
