# socialmedia

Two subprojects live in this repository:

1. **social-media-scraping-apis** (repo root + `social-media-apis-3268/`) — a
   unified HTTP API for retrieving creator profiles and posts from major
   social platforms (Twitter/X, Instagram, TikTok, YouTube), plus a
   follow-creator endpoint per platform.
2. **[OpenMontage](./openmontage/)** — a vendored build of
   [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage), the
   open-source agentic video production system. See
   [OpenMontage setup](#openmontage) below.

## social-media-scraping-apis

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

## OpenMontage

[`openmontage/`](./openmontage/) is a working build of
[calesthio/OpenMontage](https://github.com/calesthio/OpenMontage)
(vendored at upstream commit `4eab34c`), the open-source agentic video
production system: you open it in an AI coding assistant, describe the
video you want, and the agent drives research, scripting, asset
generation, editing, and final Remotion/HyperFrames composition.
It is AGPLv3-licensed — see `openmontage/LICENSE`.

### Setup

```bash
cd openmontage
make setup          # venv + Python deps + Remotion npm install + Piper TTS + .env
```

Requires Python 3.10+, Node 18+, and FFmpeg. Add API keys to
`openmontage/.env` to unlock cloud image/video/TTS providers — with zero
keys you still get Piper narration, free stock/archive footage, Remotion
composition, subtitles, and FFmpeg post-production.

### Verify

```bash
cd openmontage
make lint           # byte-compile core tools
make test           # full pytest suite
make preflight      # tool registry provider menu
make demo           # zero-key Remotion demo renders
```

### Local changes vs upstream

- **Self-hosted fonts** (`remotion-composer/src/fonts.ts`,
  `remotion-composer/public/fonts/`): the stock compositions loaded Space
  Grotesk and Playfair Display from the Google Fonts CDN inside the render
  browser, which fails in offline/locked-down environments (including some
  CI sandboxes whose TLS-inspecting egress rejects Chromium's handshake).
  The two families are now bundled as OFL-licensed latin variable fonts,
  inlined into the bundle as `data:` URLs (webpack `asset/inline`, see
  `remotion-composer/remotion.config.ts`) and registered by a hardened
  local loader (`src/fonts.ts`) whose `delayRender()` handle can never
  time a render out, so font loading makes zero network requests. No
  visual change.
- On headless hosts without a Remotion-managed browser, pass
  `--browser-executable <path-to-chromium>` to `npx remotion render`
  (Playwright's Chromium or `chrome-headless-shell` both work).
