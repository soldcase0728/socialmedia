#!/usr/bin/env bash
#
# Phase 1 -- structural inventory (portable wrapper).
#
# On macOS prefer ./scripts/run_phase1_mac.sh, which performs pre-flight
# safety checks before invoking the CLI.
#
# This wrapper assumes paths.source_folder is already set in config.yaml.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
[[ -x "${PYTHON}" ]] || PYTHON="python3"

cd "${PROJECT_ROOT}"
echo "Phase 1 -- structural inventory (no document content is read)"
exec "${PYTHON}" -m src.cli phase1 "$@"
