#!/usr/bin/env bash
#
# Run the unit tests.
#
# Every test builds its own synthetic PDFs in a temporary directory. No test
# reads, writes, or otherwise touches a real production folder.
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
[[ -x "${PYTHON}" ]] || PYTHON="python3"

cd "${PROJECT_ROOT}"
echo "Running tests against synthetic fixtures only..."
exec "${PYTHON}" -m pytest tests -v "$@"
