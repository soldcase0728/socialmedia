# Follow Creator

Each platform exposes a follow endpoint:

```
POST /{platform}/creators/{handle}/follow
```

Where `{platform}` is one of `twitter`, `instagram`, `tiktok`, `youtube`
and `{handle}` is the creator's handle (without `@`).

## Request body

```json
{
  "handle": "string (optional, defaults to the path handle)",
  "notify": false
}
```

| Field    | Type    | Default | Description                                    |
| -------- | ------- | ------- | ---------------------------------------------- |
| `handle` | string  | path    | Override target handle. Strips leading `@`.    |
| `notify` | boolean | `false` | Enable post notifications for the creator.     |

## Response

```json
{
  "platform": "instagram",
  "handle": "creatorname",
  "followed": true,
  "already_following": false,
  "notifications_enabled": false,
  "followed_at": "2026-05-11T16:51:00Z",
  "message": "Follow recorded via authenticated session."
}
```

## Status codes

| Code | Meaning                                                               |
| ---- | --------------------------------------------------------------------- |
| 200  | Follow recorded.                                                      |
| 401  | Credentials for the platform are missing (e.g. `INSTAGRAM_SESSION_ID`). |
| 404  | Creator/handle not found.                                             |
| 502  | Upstream platform returned an error.                                  |

## Per-platform notes

### Twitter / X

The v2 `POST /2/users/:id/following` endpoint requires OAuth 2.0 user
context. With only a `TWITTER_BEARER_TOKEN` (app-only), this endpoint
verifies the creator exists and returns a follow result; wire your own
OAuth user-token flow to actually issue the follow.

### Instagram

Requires `INSTAGRAM_SESSION_ID` (the `sessionid` cookie from a logged-in
session). The endpoint calls Instagram's web `friendships/create/` flow
under that session.

### TikTok

Requires `TIKTOK_SESSION_ID`. Profile lookup is performed via the public
web payload; the follow call uses the authenticated session.

### YouTube

YouTube "follows" map to channel subscriptions. The Data API
`subscriptions.insert` call needs an OAuth 2.0 user token, not an API
key — the endpoint confirms the channel exists and returns a follow
result for the caller to complete with its own OAuth flow.

## Example

```bash
curl -X POST http://localhost:8000/instagram/creators/natgeo/follow \
  -H "Content-Type: application/json" \
  -d '{"notify": true}'
```

## Responsible use

Only follow accounts on behalf of users who have authorized the action.
Automated mass-following is against the Terms of Service of every platform
listed above and is not the intended use of this endpoint.
