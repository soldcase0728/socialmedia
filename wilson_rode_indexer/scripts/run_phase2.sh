#!/usr/bin/env bash
#
# Phase 2 -- text and page-condition audit.
#
# Runs the PILOT by default. The pilot processes a stratified sample so its
# accuracy can be measured before the whole production is touched.
#
#   ./scripts/run_phase2.sh              # pilot (default)
#   ./scripts/run_phase2.sh --full       # whole production, after a pilot
#
# OCR stays disabled unless config.yaml enables it or you pass --ocr.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
[[ -x "${PYTHON}" ]] || PYTHON="python3"

MODE="--pilot"
ARGS=()
for arg in "$@"; do
    case "${arg}" in
        --full)  MODE="--full" ;;
        --pilot) MODE="--pilot" ;;
        *)       ARGS+=("${arg}") ;;
    esac
done

cd "${PROJECT_ROOT}"
echo "Phase 2 ${MODE} -- text and page-condition audit"
echo "Extracted text is stored only in the local SQLite index."
exec "${PYTHON}" -m src.cli phase2 "${MODE}" "${ARGS[@]+"${ARGS[@]}"}"
