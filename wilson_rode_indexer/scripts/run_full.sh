#!/usr/bin/env bash
#
# Full pipeline -- Phase 1, Phase 2 pilot, then STOP.
#
# This script deliberately stops after the Phase 2 pilot. Running the full
# Phase 2 and Phase 3 over the entire production is a separate, explicit
# decision that should follow a review of the pilot's accuracy.
#
#   ./scripts/run_full.sh                 # phase 1 + phase 2 pilot, then stop
#   ./scripts/run_full.sh --continue      # also run phase 2 full + phase 3
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
[[ -x "${PYTHON}" ]] || PYTHON="python3"

CONTINUE=0
for arg in "$@"; do
    [[ "${arg}" == "--continue" ]] && CONTINUE=1
done

cd "${PROJECT_ROOT}"

echo "=================================================================="
echo "Phase 1 -- structural inventory"
echo "=================================================================="
"${PYTHON}" -m src.cli phase1

echo
echo "=================================================================="
echo "Phase 2 -- pilot sample"
echo "=================================================================="
"${PYTHON}" -m src.cli phase2 --pilot

if [[ "${CONTINUE}" -eq 0 ]]; then
    echo
    echo "=================================================================="
    echo "STOPPED after the Phase 2 pilot, by design."
    echo
    echo "  1. Read Phase_2_Pilot_Summary.md"
    echo "  2. Review the QC sample and measure accuracy"
    echo "  3. Adjust config.yaml if the pilot exposed problems"
    echo "  4. Re-run with --continue to process the whole production"
    echo "=================================================================="
    exit 0
fi

echo
echo "=================================================================="
echo "Phase 2 -- full production"
echo "=================================================================="
"${PYTHON}" -m src.cli phase2 --full

echo
echo "=================================================================="
echo "Phase 3 -- derived document metadata"
echo "=================================================================="
"${PYTHON}" -m src.cli phase3

echo
echo "=================================================================="
echo "Quality-control sample"
echo "=================================================================="
"${PYTHON}" -m src.cli qc-sample

echo
echo "Done. Read Final_Run_Summary.md, then work through QC_Sample.xlsx."
