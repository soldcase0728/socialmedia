# The St. Mary's Content & Enrollment Marketing Operating System

This is not a social media plan. It is a closed loop that turns ordinary days at
Orchard Lake St. Mary's into evidence, evidence into stories, stories into
enrollment demand -- and results back into better stories.

```
CAPTURE -> TRIAGE -> CREATE -> APPROVE -> PUBLISH -> MEASURE -> LEARN -> CAPTURE
```

Two questions govern everything in it:

> **Parents:** Why should a family entrust an important period of their child's
> formation to St. Mary's?
>
> **Students:** Why would I want to spend the next four years of my life here?

They are related. They are not the same question, and one generic admissions
message will not answer both. Every piece of content this system produces names
which one it is answering.

## What is in this repository

| Layer | Where |
| --- | --- |
| Brand position, pillars, language discipline | `brandops/brand.py`, [01-brand.md](01-brand.md) |
| Audience segments | `brandops/audiences.py`, [02-audiences.md](02-audiences.md) |
| Capture machine and intake | `brandops/capture.py`, `brandops/assets.py`, [03-capture.md](03-capture.md) |
| Triage and the opportunity score | `brandops/triage.py`, `brandops/scoring.py`, [04-triage-and-scoring.md](04-triage-and-scoring.md) |
| Packages, hooks, copy, production | `brandops/packages.py`, `hooks.py`, `copywriting.py`, [05-production-and-copy.md](05-production-and-copy.md) |
| Approval, calendars, distribution | `brandops/approval.py`, `calendar.py`, [06-approval-and-distribution.md](06-approval-and-distribution.md) |
| Measurement and brand memory | `brandops/measurement.py`, `memory.py`, [07-measurement-and-memory.md](07-measurement-and-memory.md) |
| Microsoft 365 build, stack and cost | `brandops/stack.py`, [08-automation-architecture.md](08-automation-architecture.md) |
| Scheduled jobs | `brandops/scheduled.py`, `scripts/`, [09-scheduling.md](09-scheduling.md) |
| Optional Claude assistance | `brandops/llm.py` |

## Running it

No installation, no dependencies, no API key:

```bash
python -m brandops today          # the morning brief
python -m brandops capture        # today's shot list for staff
python -m brandops triage         # rank the inbox
python -m brandops queue list     # the approval queue
python -m brandops weekly --learn # the weekly report, folded into brand memory
python -m brandops stack          # software cost per hour saved
```

State is JSON under `data/`. Point `BRANDOPS_DATA` at a synced SharePoint or
OneDrive folder and the whole team shares one state file.

To run it unattended each morning, see [09-scheduling.md](09-scheduling.md) --
`scripts/daily-brief.sh` (cron) and `scripts/daily-brief.ps1` (Task Scheduler)
each need exactly two paths edited.

## The daily rhythm

| When | Who | What | Command |
| --- | --- | --- | --- |
| 7:15 am | *(scheduled)* | Brief and capture list written to the shared folder | `run-daily` |
| 7:45 am | Marketing | Read the brief, send the capture list | `today`, `capture` |
| All day | Staff | Shoot, scan the QR code, upload | (phone) |
| 2:00 pm | Marketing | Triage, draft, queue | `triage`, `queue build` |
| 3:00 pm | Approver | Approve, edit, reject or hold | `queue list`, `queue approve` |
| 3:30 pm | Marketing | Schedule | native schedulers |
| Friday 3:30 | *(scheduled)* | Weekly report written, folded into memory | `run-weekly` |
| Friday | Marketing | Record results, read the report | `record`, `weekly --learn` |
| Monthly | Marketing + Admissions | Mix, calendar, campaign review | `mix`, `plan 30`, `plan 90` |

## First thirty days

1. **Week 1 -- fill in the blanks.** Set links and handles in `brandops/config.py`.
   Replace the template school calendar in `brandops/calendar.py` with the real
   one. Replace the seeded objection library in `brandops/memory.py` with what
   the admissions office actually hears on the phone.
2. **Week 1 -- build the inbox.** Follow [08-automation-architecture.md](08-automation-architecture.md).
   One group form, one SharePoint library, one list, one approval flow. Print
   the QR code (`python -m brandops onepager`) and put it on classroom doors.
3. **Week 2 -- run capture with five willing teachers.** Not the whole faculty.
   Five people who will actually do it, so the first week produces something.
4. **Week 3 -- schedule the morning job** ([09-scheduling.md](09-scheduling.md)),
   then publish and record every result. The system is worthless until
   `record` has data in it; every recommendation before that is a guess wearing
   a number.
5. **Week 4 -- read the first weekly report** with `--learn`, and change one thing
   because of it. One. Then keep going.

## The operating principle

The goal is not to make St. Mary's look like it has a great marketing
department. The goal is to let people see enough authentic evidence that they
reach the conclusion themselves:

> Something different is happening at St. Mary's.
