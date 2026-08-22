# From Footage to Published Content

## One event is a package, not a post

`python -m brandops package "AP Chemistry lab"` turns one classroom visit into
ten outputs:

| Published | Banked |
| --- | --- |
| Instagram Reel (25s) | pull quote -> brand memory |
| TikTok (18s, rougher, student voice) | website / viewbook image |
| YouTube Short (35s, titled for search) | evergreen library entry, tagged by pillar |
| Instagram Story (10s, same day) | |
| Facebook post (context for parents) | |
| Instagram feed still | |
| Paid creative test (if it qualifies) | |

The banked half is where compounding value lives. A quote captured in September
is still working in February when the outcomes pillar runs thin.

## Production standards

Everyday storytelling is cut fast and stays visibly authentic. Over-produced
ordinary content reads as advertising and performs like it. Save polish for
major brand campaigns.

The standard fast pass:

1. Pull the three strongest clips; cut everything before the action starts.
2. Trim dead air -- no clip opens on someone walking into frame.
3. Auto-transcribe, then pull the single best student or teacher sentence.
4. Burn in captions. Most of this is watched silent.
5. Clean the audio: reduce room noise, level the voice, music under speech.
6. Crop to 9:16 around the subject rather than re-shooting.
7. On-screen hook over the first frame, gone by 2.5 seconds.

Campaign pass adds color matching, a real mix, B-roll over every cut, and
15/30/45-second versions from one timeline.

## Hooks

The first one to three seconds decide whether anything else is seen. Every
short-form cut gets at least three options from ten structures (`brandops/hooks.py`):

unexpected statement · parent concern · student question · transformation ·
curiosity · contradiction · surprising statistic · behind the scenes ·
emotional moment · what-this-actually-looks-like

Two rules are enforced in code:

- **No invented facts.** A structure whose fact is missing is skipped, not
  filled. "In September, ___ could not ___" only generates when a real
  before-state was supplied. A statistic hook only generates from a supplied
  statistic, and is flagged for verification.
- **No clickbait.** Generated hooks are run through the same lint as captions.

## Platform-specific copy

Never paste the same text across five surfaces. The same story is adapted:

| Platform | What it carries |
| --- | --- |
| **Instagram Reels** | visual storytelling; identity, belonging, aspiration |
| **Instagram feed** | one strong frame; first line is the hook |
| **Stories** | same-day, unpolished, interactive |
| **Facebook** | the trust surface; longest copy; explicit CTA |
| **TikTok** | authentic, immediate, student-voiced -- **and no CTA** |
| **YouTube Shorts** | titled the way a parent would search it |
| **YouTube** | the full story, evergreen |
| **LinkedIn** | outcomes, faculty, institution -- never student life |

Adults do not imitate teenage slang. The lint flags it. Student voice belongs to
students; put the words in a student's mouth or cut them.

Every draft is checked before it can be queued: banned phrases, clickbait,
unset links, unverified statistics, adult slang, and caption length against the
platform's range.

## Paid vs. organic

Different jobs, tracked separately.

**Organic** builds familiarity, identity, trust and community over time. Its job
is to be seen repeatedly and believed slowly.

**Paid** moves a defined audience along awareness -> interest -> visit -> inquiry
-> application -> enrollment. Every paid creative must declare six things before
it spends a dollar:

1. an identifiable audience
2. a psychological objective
3. a strong hook
4. a clear proposition
5. proof
6. a call to action and how it will be measured

Boosting a post that did well organically is not an advertising strategy. The
engine proposes paid creative as a **test**, derived from an organic winner but
rebuilt with its own ending, its own CTA and its own measurement plan. See
`templates/paid-brief.md`.
