# social-media-scraping-apis

A unified HTTP API for retrieving creator profiles and posts from major social
platforms (Twitter/X, Instagram, TikTok, YouTube), plus a follow-creator
endpoint per platform.

## Layout

```
.
├── app.py                       # ASGI entry point (uvicorn app:app)
├── requirements.txt
├── settings/                    # Pydantic settings + .env.example
│   ├── config.py
│   └── .env.example
└── social-media-apis-3268/      # FastAPI app package
    ├── main.py                  # create_app() + router wiring
    ├── models.py                # Creator, Post, Follow* schemas
    ├── routes/                  # one router per platform
    └── scrapers/                # one async scraper per platform
```

The package directory contains a hyphen and is loaded under the importable
alias `social_media_apis_3268` by `app.py`.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp settings/.env.example .env
# fill in credentials for the platforms you need
uvicorn app:app --reload
```

Open <http://localhost:8000/docs> for the interactive API.

## Endpoints

For each platform (`twitter`, `instagram`, `tiktok`, `youtube`):

| Method | Path                                       | Purpose                       |
| ------ | ------------------------------------------ | ----------------------------- |
| GET    | `/{platform}/creators/{handle}`            | Fetch creator profile         |
| GET    | `/{platform}/creators/{handle}/posts`      | Fetch recent posts (`?limit`) |
| POST   | `/{platform}/creators/{handle}/follow`     | Follow a creator              |

The follow endpoint is documented in [FOLLOW_CREATOR.md](./FOLLOW_CREATOR.md).

## Credentials

Each platform reads its credentials from environment variables:

| Variable                | Used by   | Notes                                |
| ----------------------- | --------- | ------------------------------------ |
| `TWITTER_BEARER_TOKEN`  | Twitter   | App-only bearer for v2 endpoints     |
| `INSTAGRAM_SESSION_ID`  | Instagram | `sessionid` cookie from a logged-in browser |
| `TIKTOK_SESSION_ID`     | TikTok    | `sessionid` cookie from a logged-in browser |
| `YOUTUBE_API_KEY`       | YouTube   | Data API v3 key                      |

Read endpoints work without credentials where the public web exposes the
data; the follow endpoints require authenticated sessions.

## Notes

- Use this only against accounts you own or have authorization to access.
  Respect each platform's Terms of Service and applicable scraping
  regulations in your jurisdiction.
- The follow endpoints for Twitter and YouTube require OAuth user context
  that this scaffold doesn't provision; they return a structured result so
  callers can plug their own OAuth flow in.
