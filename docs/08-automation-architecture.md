# Automation Architecture, Stack and Cost

## The principle

Before recommending any new software:

1. Can Microsoft 365 do it? (SharePoint, Forms, Power Automate, Lists, Teams, Clipchamp)
2. Can the chat subscription we already pay for do it?
3. Can the platform's own native tools do it?
4. **Only then:** does a paid application save more hours than it costs?

Never pay separately for idea generation, captions, social scheduling,
analytics, AI rewriting, content calendars or file storage. The stack already
covers all seven.

```bash
python -m brandops stack
```

## The build, end to end

```
Phone -> QR code -> Microsoft Form -> SharePoint content inbox
                                            |
                             Power Automate: create queue item
                                            |
                          python -m brandops triage / today
                                            |
                        Drafts + hooks + copy -> approval queue
                                            |
                Power Automate: Start and wait for an approval -> Teams
                                            |
                     Native schedulers (Meta, TikTok, YouTube)
                                            |
                  python -m brandops record -> weekly --learn
                                            |
                                    brand memory
```

### 1. Content inbox (SharePoint + Forms)

Create the intake form as a **group form** owned by the marketing Microsoft 365
group, not as a personal form. Group-form file uploads are stored in that
group's SharePoint site; personal-form uploads land in one person's OneDrive and
become a single point of failure the day they leave.

Add a **File upload** question plus the four required text questions from
[03-capture.md](03-capture.md). Microsoft Forms generates a **QR code** on its
share panel -- that is the code that goes on classroom doors.

### 2. Intake flow (Power Automate)

Trigger: **When a new response is submitted** (Forms)
→ **Get response details**
→ **Create item** in a SharePoint list called `Content Queue`

Columns to create on the list:

| Column | Type | Notes |
| --- | --- | --- |
| AssetId | Single line | matches `asset_id` from the engine |
| Event, Department, Contributor, Description | Single line / multi-line | from the form |
| CapturedAt | Date | |
| ConsentOK, Sensitive, PublishNowOK | Yes/No | defaults per the form |
| Pillar, Audience, Platform | Choice | written back after triage |
| Score | Number | out of 50 |
| Status | Choice | RAW / REVIEWED / CONTENT_OPPORTUNITY / DRAFTED / APPROVED / SCHEDULED / PUBLISHED / MEASURED / LIBRARY / REJECTED |
| ScheduledFor | Date and time | |
| Approver, DecidedBy | Person | |

### 3. Triage

Point `BRANDOPS_DATA` at a OneDrive-synced folder so the whole team shares one
state file, export the list to the engine, and run:

```bash
python -m brandops today      # the morning brief
python -m brandops triage     # ranked inbox
python -m brandops queue build "<event>"
```

Two ways to run it, in cost order:

- **Recommended:** the person who owns the queue runs the CLI once or twice a
  day. Zero infrastructure, zero incremental cost, and a human sees every asset.
- **If volume justifies it:** a scheduled flow (or Power Automate Desktop /
  Azure Function) invokes the same CLI on a timer and writes results back to the
  list. Do not build this until the manual version is genuinely the bottleneck.

### 4. Approval flow (Power Automate)

Trigger: **When an item is created or modified** (SharePoint, `Content Queue`),
filtered to `Status = DRAFTED`
→ **Start and wait for an approval** — approval type *Approve/Reject – First to
respond*; **Assigned to** the routed approver (see the routing table in
[06-approval-and-distribution.md](06-approval-and-distribution.md)); **Details**
carries the caption, platform, purpose and score
→ **Condition** on the approver response
→ update `Status` to APPROVED or REJECTED, write `DecidedBy`
→ post the outcome to the marketing Teams channel

Approvers respond from Outlook, Teams, or the Power Automate mobile app. Nothing
new to learn and nothing new to buy.

### 5. Distribution

Native schedulers only, until someone is posting to five or more accounts a
week: Meta Business Suite (Facebook + Instagram), TikTok's scheduler, YouTube
Studio. Free, first-party, and the analytics are better than the resold versions.

### 6. Measurement

Weekly recurrence flow posts a Teams reminder. The queue owner records results
and runs `python -m brandops weekly --learn`. UTM tags on every link, GA4 for the
landing pages -- without those, every claim about what converts is a guess.

## Stack and cost

| Tool | Purpose | Monthly | Existing alternative | Labor saved | Essential? |
| --- | --- | --- | --- | --- | --- |
| Microsoft 365 | inbox, form, routing, queue, approvals | $0 (licensed) | this IS the alternative to four SaaS products | 3.0 hrs/wk | Essential |
| Claude or ChatGPT (1 seat) | ideation, captions, hooks, edit plans, analysis | $20-30 | none at this quality | 4.0 hrs/wk | Essential |
| Native schedulers | scheduling + first-party analytics | $0 | this IS the alternative to a paid scheduler | 1.5 hrs/wk | Essential |
| CapCut / Adobe Express | vertical cutting, captions, audio | $0-15 | Clipchamp is included with M365 | 2.5 hrs/wk | Essential |
| GA4 + UTM | connect campaigns to admissions behavior | $0 | this IS the alternative to an attribution product | 0.5 hrs/wk | Essential |
| Canva Teams | quote cards, templates for non-designers | $10-15 | PowerPoint templates (owned) | 1.0 hrs/wk | Optional |
| Cross-platform scheduler | one queue and one analytics view | $25-100 | native + a Microsoft List | 2.0 hrs/wk | Optional |
| Paid social budget | admissions campaigns | $300-1500 | none -- this is media, not software | -- | Separate line |

Figures are budget estimates as of 2026-08; confirm current vendor pricing
before purchase. Run `python -m brandops stack` for the live math.

**Essential stack: roughly $390/year against about 460 staff hours saved across
a 40-week school year -- under a dollar per hour saved.** Optimize for that
ratio, not for feature count. Media budget is tracked separately and is not part
of the software figure.

## What we deliberately did not build

- A digital asset management system. SharePoint with metadata columns is one.
- A workflow product. Power Automate is one.
- An AI captioning subscription. The chat seat already writes captions.
- A social listening platform. Nothing about it would change what we shoot
  tomorrow morning.
- A database. Flat JSON a human can open, read and correct is a feature at this
  scale, not a compromise.
