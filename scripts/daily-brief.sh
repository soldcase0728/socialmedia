#!/usr/bin/env bash
# Morning content-engine job (macOS / Linux).
#
# Install with `crontab -e`:
#   15 7 * * 1-5  /path/to/socialmedia/scripts/daily-brief.sh
#   30 15 * * 5   /path/to/socialmedia/scripts/daily-brief.sh weekly
#
# Edit the two paths below and nothing else.

set -euo pipefail

# --- edit these two ---------------------------------------------------------
# Where the shared state lives. Point this at the synced SharePoint/OneDrive
# folder so the job, the marketing office and the approver all see one state.
export BRANDOPS_DATA="${BRANDOPS_DATA:-$HOME/OneDrive - Orchard Lake St Marys/Marketing/brandops-data}"
# Where the brief and capture list are written for the team to read.
export BRANDOPS_OUT="${BRANDOPS_OUT:-$HOME/OneDrive - Orchard Lake St Marys/Marketing/briefs}"
# ----------------------------------------------------------------------------

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${BRANDOPS_PYTHON:-python3}"
LOG="${BRANDOPS_LOG:-$REPO/briefs.log}"
JOB="${1:-daily}"

cd "$REPO"

# Capture the job's status without errexit aborting first (`|| status=$?` is
# exempt from set -e), and without reading $? after an `if`, which would report
# the status of the `if` itself rather than the job.
status=0
{
  echo "--- $(date '+%Y-%m-%d %H:%M:%S') running $JOB ---"
  if [ "$JOB" = "weekly" ]; then
    "$PYTHON" -m brandops run-weekly
  else
    "$PYTHON" -m brandops run-daily
  fi
} >> "$LOG" 2>&1 || status=$?

if [ "$status" -ne 0 ]; then
  echo "brandops $JOB job FAILED -- see $LOG and the ERROR file in $BRANDOPS_OUT" >&2
fi
exit "$status"
