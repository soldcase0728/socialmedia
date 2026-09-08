# OLSM Admissions

Public admissions site for **Orchard Lake St. Mary's Preparatory** — a Catholic
co-divisional college-preparatory high school in Orchard Lake, Michigan, founded 1885.

Applications are handled in Blackbaud. This site has four jobs: be found, be
believed, get families to an open house or shadow day, and capture an inquiry.

## Stack

- [Astro](https://astro.build) 7, TypeScript, Tailwind CSS 4
- Static HTML output; two server endpoints (`/api/inquiry`, `/api/rsvp`) and one
  redirect (`/visit`) run as Vercel functions via `@astrojs/vercel`
- Content in Markdown/MDX under `src/content/`
- No client-side rendering of text. Every sentence is in the HTML.

## Local development

```bash
npm install
cp .env.example .env   # fill in what you have; empty vars simply disable a tag
npm run dev            # http://localhost:4321
npm run build          # must stay clean
npm run check          # astro check (types + templates)
```

## Deploying

Vercel, with **Root Directory** set to `olsm-admissions/`. `vercel.json` pins the
framework, build command and security headers.

### Environment variables

| Variable | Scope | Purpose |
| --- | --- | --- |
| `PUBLIC_GA4_ID` | Client | GA4 measurement ID. No tag renders when empty. |
| `PUBLIC_META_PIXEL_ID` | Client | Meta Pixel ID. No tag renders when empty. |
| `RESEND_API_KEY` | Server | Sends inquiry and RSVP notification email. |
| `SHEET_WEBHOOK_URL` | Server | Google Apps Script webhook that appends a row per submission. |

## Measured quality

Mobile Lighthouse against the production build (`npm run build`, served over
HTTP at 390px, Moto G class throttling):

| Page | Performance | Accessibility | Best practices | SEO |
| --- | --- | --- | --- | --- |
| `/` | 100 | 100 | 100 | 100 |
| `/shadow-days` | 99 | 100 | 100 | 100 |

To re-run against a deployed URL:

```bash
npx lighthouse https://<preview-url>/ --form-factor=mobile --preset=desktop=false \
  --only-categories=performance,accessibility,best-practices,seo --view
```

## Editing the facts

Everything that changes between admission cycles lives in
[`src/config/site.ts`](src/config/site.ts): the announcement bar text, open house
date, phone number, Blackbaud application URL, Calendly link, proof stats and
social profiles. Change it there once; no page markup hard-codes a date or a URL.

Anything not yet confirmed by the school is marked `TODO: confirm` in the source.
Milestone 5 prints the full checklist grouped by page.

## Facts still to confirm

`CONTENT-CHECKLIST.md` is generated from the source and lists every unconfirmed
fact, grouped by the page it appears on. Regenerate it after any content change:

```bash
npm run todos              # grouped checklist in the terminal
npm run todos -- --md > CONTENT-CHECKLIST.md
```

## UTM convention

Every off-site link into this site carries UTM parameters. `/visit` is the short
path for print and QR codes; it 302s to `/events-on-campus` and preserves the
full query string, so tags survive the hop.

- **`utm_source`** — where the click came from. Use one of:
  `facebook`, `instagram`, `email`, `flyer`, `bulletin`, `geofence`, `yard-sign`,
  `grade-school`, `press`.
- **`utm_medium`** — the kind of placement:
  `paid-social`, `organic-social`, `email`, `print`, `display`, `referral`, `qr`.
- **`utm_campaign`** — the push. One per event, kebab-case, ending in the date:
  `open-house-oct18`. Shadow-day evergreen traffic uses `shadow-days-evergreen`.
- **`utm_content`** — optional, to split creative: `carousel-a`, `postcard-back`.

Examples:

```text
https://www.olsmadmissions.com/visit?utm_source=facebook&utm_medium=paid-social&utm_campaign=open-house-oct18&utm_content=carousel-a
https://www.olsmadmissions.com/visit?utm_source=bulletin&utm_medium=print&utm_campaign=open-house-oct18
https://www.olsmadmissions.com/shadow-days?utm_source=email&utm_medium=email&utm_campaign=shadow-days-evergreen
```

Both forms fire a GA4 event on success — `generate_lead` for the inquiry form,
`rsvp` for the open house form — so campaign attribution reaches conversions.

## Writing rules for content

Plain sentences with a number, a name or a time. The first sentence answers the
question asked by the page title. Banned: "unlock potential", "holistic
excellence", "journey", "prepare for success", and "prepare/prepared" as a
headline word.
