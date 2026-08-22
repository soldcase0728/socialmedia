# Morning content-engine job (Windows).
#
# Register with Task Scheduler (run once, in an elevated PowerShell):
#   schtasks /create /tn "St Marys content brief" /sc weekly /d MON,TUE,WED,THU,FRI /st 07:15 `
#     /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\socialmedia\scripts\daily-brief.ps1"
#   schtasks /create /tn "St Marys weekly report" /sc weekly /d FRI /st 15:30 `
#     /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\socialmedia\scripts\daily-brief.ps1 weekly"
#
# Edit the two paths below and nothing else.

param([string]$Job = "daily")

$ErrorActionPreference = "Stop"

# --- edit these two ---------------------------------------------------------
# Where the shared state lives (the synced SharePoint/OneDrive folder).
$env:BRANDOPS_DATA = "$env:USERPROFILE\OneDrive - Orchard Lake St Marys\Marketing\brandops-data"
# Where the brief and capture list are written for the team to read.
$env:BRANDOPS_OUT  = "$env:USERPROFILE\OneDrive - Orchard Lake St Marys\Marketing\briefs"
# ----------------------------------------------------------------------------

$repo = Split-Path -Parent $PSScriptRoot
$python = if ($env:BRANDOPS_PYTHON) { $env:BRANDOPS_PYTHON } else { "python" }
$log = Join-Path $repo "briefs.log"

Set-Location $repo

$command = if ($Job -eq "weekly") { "run-weekly" } else { "run-daily" }

"--- $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') running $Job ---" | Out-File -Append $log
& $python -m brandops $command *>> $log

if ($LASTEXITCODE -ne 0) {
    Write-Error "brandops $Job job FAILED -- see $log and the ERROR file in $env:BRANDOPS_OUT"
    exit $LASTEXITCODE
}
