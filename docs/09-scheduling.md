# Scheduling the Jobs

Two unattended jobs. Both run on the machine where the content inbox is synced,
because that is the only place the assets actually are.

| Job | When | Produces |
| --- | --- | --- |
| `run-daily` | weekday mornings, ~7:15 | `brief-YYYY-MM-DD.md` + `capture-YYYY-MM-DD.md` |
| `run-weekly` | Friday afternoon, ~15:30 | `weekly-YYYY-MM-DD.md`, folded into brand memory |

Each also refreshes a stable `*-latest.md`, so a Power Automate flow can watch
one filename forever.

## Why the school machine

The morning brief has two halves. The **calendar half** -- what is happening this
week, capture assignments, funnel phase -- could run anywhere. The **triage
half** -- today's strongest stories, hooks, drafted copy -- needs the content
inbox, which lives wherever `BRANDOPS_DATA` points. A cloud job cloning this
repository gets an empty `data/` folder (it is gitignored, deliberately: student
names and unpublished drafts do not belong in git) and would produce a brief
with an empty inbox every morning.

So: run it where the files are.

## Two paths to set

Both wrapper scripts have exactly two lines to edit:

```
BRANDOPS_DATA  -> the synced SharePoint/OneDrive folder holding shared state
BRANDOPS_OUT   -> where briefs are written for the team to read
```

Point `BRANDOPS_DATA` at a synced folder and the job, the marketing office and
the approver all read one state. Point it at a local folder and only that
machine sees anything.

## macOS / Linux

```bash
crontab -e
```

```cron
15 7 * * 1-5  /path/to/socialmedia/scripts/daily-brief.sh
30 15 * * 5   /path/to/socialmedia/scripts/daily-brief.sh weekly
```

On macOS, `cron` needs Full Disk Access to read a synced OneDrive folder:
System Settings → Privacy & Security → Full Disk Access → add `/usr/sbin/cron`.
Without it the job fails with a permission error, which is written to the
`ERROR-*.md` file rather than swallowed.

## Windows

In an elevated PowerShell, once:

```powershell
schtasks /create /tn "St Marys content brief" /sc weekly /d MON,TUE,WED,THU,FRI /st 07:15 `
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\socialmedia\scripts\daily-brief.ps1"

schtasks /create /tn "St Marys weekly report" /sc weekly /d FRI /st 15:30 `
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\socialmedia\scripts\daily-brief.ps1 weekly"
```

In Task Scheduler's GUI, set the task to **Run whether user is logged on or
not** and **Run task as soon as possible after a scheduled start is missed** --
otherwise a laptop that was asleep at 7:15 silently produces nothing.

## Delivering it to the team

The job writes files; it does not send mail. Delivery uses what the school
already owns:

**Power Automate → Teams.** Trigger: *When a file is created or modified*
(SharePoint), on the briefs folder, filtered to `capture-latest.md`
→ *Get file content* → *Post message in a chat or channel*, to the marketing
channel. Teachers get the shot list in Teams by 7:20 without anyone forwarding
anything.

Watch `capture-latest.md`, not `brief-latest.md`. The capture list is written as
a separate file precisely because it is the half that gets forwarded to staff --
nobody should be forwarding a document with draft ad copy and paid-media notes
in it.

## Confirming it actually ran

A scheduled job that fails quietly is worse than no scheduled job, because the
office keeps believing a brief was produced. Three checks:

1. `briefs.log` in the repository root — every run appends a timestamped line.
2. An `ERROR-YYYY-MM-DD.md` file in the output folder means the job failed and
   the traceback is inside it. Both jobs exit non-zero, so Task Scheduler shows
   a failed result too.
3. `brief-latest.md` should carry today's date at the top. A stale date means
   the job has not run since then.

Add a second Power Automate flow if you want it pushed: *When a file is created*
on `ERROR-*` → post to the marketing channel.

## What the job does not do

It does not publish, approve, or schedule posts. It prepares. A named human
still approves every card (`python -m brandops queue approve <card> --by "..."`),
and that gate has no bypass — least of all an unattended one.
