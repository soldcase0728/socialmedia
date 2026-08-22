# socialmedia

Two projects live here.

## 1. `brandops/` — St. Mary's content & enrollment marketing operating system

A closed loop that turns ordinary days at Orchard Lake St. Mary's into evidence,
evidence into stories, and results back into better stories:

```
CAPTURE -> TRIAGE -> CREATE -> APPROVE -> PUBLISH -> MEASURE -> LEARN -> CAPTURE
```

Pure standard library, no API key required. Start with
**[docs/00-start-here.md](docs/00-start-here.md)**.

```bash
python -m brandops today          # the morning brief: today's stories, hooks, copy, capture list
python -m brandops capture        # today's shot list for staff
python -m brandops triage         # rank the content inbox
python -m brandops queue list     # the approval queue
python -m brandops weekly --learn # weekly intelligence report, folded into brand memory
python -m brandops stack          # software cost per staff hour saved
python -m brandops run-daily      # unattended morning job (cron / Task Scheduler)
```

| | |
| --- | --- |
| Documentation | [`docs/`](docs/) — brand, audiences, capture, triage, production, approval, measurement, architecture |
| Templates | [`templates/`](templates/) — intake form, capture card, approval card, paid brief, weekly report |
| Scheduling | [`docs/09-scheduling.md`](docs/09-scheduling.md), `scripts/daily-brief.sh` / `.ps1` |
| Tests | `pytest tests/` |

Optional Claude assistance (`brandops/llm.py`) is off by default; every generator
also renders a paste-ready prompt so the step can be run in a chat subscription
the school already pays for. See [docs/08-automation-architecture.md](docs/08-automation-architecture.md)
for the Microsoft 365 build and the cost discipline behind it.

---

## 2. `social-media-scraping-apis` — creator profile & post API

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
