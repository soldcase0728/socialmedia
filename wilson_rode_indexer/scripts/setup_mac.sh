#!/usr/bin/env bash
#
# macOS setup for the Wilson-Rode derived index.
#
# Creates a virtual environment, installs the Python dependencies, and REPORTS
# on Homebrew / Tesseract / OCRmyPDF availability.
#
# This script never installs OCR tooling and never runs OCR. It only tells you
# whether the tools are present and prints the command you would run yourself
# if you decide you want them.
#
# Usage:
#   ./scripts/setup_mac.sh
#   ./scripts/setup_mac.sh --python /opt/homebrew/bin/python3.12
#   ./scripts/setup_mac.sh --show-ocr-install    # print OCR install commands only
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
PYTHON_BIN=""
SHOW_OCR_INSTALL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python)
            PYTHON_BIN="${2:-}"
            shift 2
            ;;
        --show-ocr-install)
            SHOW_OCR_INSTALL=1
            shift
            ;;
        -h|--help)
            sed -n '2,20p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

say()  { printf '%s\n' "$*"; }
ok()   { printf '  [ok]      %s\n' "$*"; }
warn() { printf '  [absent]  %s\n' "$*"; }
bad()  { printf '  [MISSING] %s\n' "$*"; }
rule() { printf '%s\n' "------------------------------------------------------------------"; }

rule
say "Wilson-Rode derived index -- macOS setup"
rule
say "Project root: ${PROJECT_ROOT}"
say ""

# ---------------------------------------------------------------------------
# 1. Locate a suitable Python 3
# ---------------------------------------------------------------------------
say "Checking Python..."
if [[ -z "${PYTHON_BIN}" ]]; then
    for candidate in python3.12 python3.11 python3.13 python3.10 python3; do
        if command -v "${candidate}" >/dev/null 2>&1; then
            PYTHON_BIN="$(command -v "${candidate}")"
            break
        fi
    done
fi

if [[ -z "${PYTHON_BIN}" ]] || ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    bad "No python3 found on PATH."
    say ""
    say "Install Python 3.12 with Homebrew:"
    say "    brew install python@3.12"
    say "Then re-run this script."
    exit 1
fi

PY_VERSION="$("${PYTHON_BIN}" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION##*.}"
if [[ "${PY_MAJOR}" -lt 3 ]] || { [[ "${PY_MAJOR}" -eq 3 ]] && [[ "${PY_MINOR}" -lt 10 ]]; }; then
    bad "Python ${PY_VERSION} is too old. Python 3.10 or newer is required."
    say "    brew install python@3.12"
    exit 1
fi
ok "Python ${PY_VERSION} at ${PYTHON_BIN}"

# ---------------------------------------------------------------------------
# 2. Homebrew (informational -- nothing is installed by this script)
# ---------------------------------------------------------------------------
say ""
say "Checking Homebrew..."
if command -v brew >/dev/null 2>&1; then
    ok "Homebrew $(brew --version 2>/dev/null | head -n1)"
    HAVE_BREW=1
else
    warn "Homebrew is not installed."
    say "          Homebrew is only needed if you later choose to install OCR"
    say "          tooling. The indexer itself does not require it."
    say "          Install it from https://brew.sh if you want OCR."
    HAVE_BREW=0
fi

# ---------------------------------------------------------------------------
# 3. OCR tooling (checked, never installed, never run)
# ---------------------------------------------------------------------------
say ""
say "Checking optional OCR tooling..."
HAVE_TESSERACT=0
HAVE_OCRMYPDF=0
if command -v tesseract >/dev/null 2>&1; then
    ok "tesseract $(tesseract --version 2>&1 | head -n1 | awk '{print $2}')"
    HAVE_TESSERACT=1
else
    warn "tesseract not found"
fi
if command -v ocrmypdf >/dev/null 2>&1; then
    ok "ocrmypdf $(ocrmypdf --version 2>/dev/null || echo '')"
    HAVE_OCRMYPDF=1
else
    warn "ocrmypdf not found"
fi

say ""
if [[ "${HAVE_TESSERACT}" -eq 1 && "${HAVE_OCRMYPDF}" -eq 1 ]]; then
    say "  OCR tooling is available, but OCR remains DISABLED until you set"
    say "  ocr.enabled: true in config.yaml or pass --ocr on the command line."
else
    say "  OCR is optional. Phase 1 never uses it, and Phase 2 only uses it for"
    say "  pages with no usable text layer. Nothing has been installed."
fi

if [[ "${SHOW_OCR_INSTALL}" -eq 1 || "${HAVE_TESSERACT}" -eq 0 || "${HAVE_OCRMYPDF}" -eq 0 ]]; then
    say ""
    say "  If you decide you want OCR later, run these yourself:"
    if [[ "${HAVE_BREW}" -eq 1 ]]; then
        say "      brew install tesseract"
        say "      brew install ocrmypdf"
    else
        say "      # install Homebrew first: https://brew.sh"
        say "      brew install tesseract ocrmypdf"
    fi
    say "  This script will not run them for you."
fi

if [[ "${SHOW_OCR_INSTALL}" -eq 1 ]]; then
    exit 0
fi

# ---------------------------------------------------------------------------
# 4. Virtual environment
# ---------------------------------------------------------------------------
say ""
rule
say "Creating the virtual environment"
rule
if [[ -d "${VENV_DIR}" ]]; then
    say "Existing virtual environment found at ${VENV_DIR}; reusing it."
else
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
    say "Created ${VENV_DIR}"
fi

VENV_PY="${VENV_DIR}/bin/python"
if [[ ! -x "${VENV_PY}" ]]; then
    bad "Virtual environment creation failed (${VENV_PY} is missing)."
    exit 1
fi

# ---------------------------------------------------------------------------
# 5. Dependencies
# ---------------------------------------------------------------------------
say ""
say "Installing Python dependencies (local only, nothing is uploaded)..."
"${VENV_PY}" -m pip install --upgrade pip >/dev/null
if [[ -f "${PROJECT_ROOT}/requirements.txt" ]]; then
    "${VENV_PY}" -m pip install -r "${PROJECT_ROOT}/requirements.txt"
else
    bad "requirements.txt not found in ${PROJECT_ROOT}"
    exit 1
fi

# ---------------------------------------------------------------------------
# 6. Verify
# ---------------------------------------------------------------------------
say ""
rule
say "Verifying the installation"
rule
"${VENV_PY}" - <<'PYCHECK'
import importlib
import sqlite3
import sys

modules = [
    ("fitz", "PyMuPDF"), ("pypdf", "pypdf"), ("pandas", "pandas"),
    ("openpyxl", "openpyxl"), ("dateutil", "python-dateutil"),
    ("rapidfuzz", "rapidfuzz"), ("tqdm", "tqdm"), ("PIL", "Pillow"),
    ("yaml", "PyYAML"),
]
missing = []
for module, label in modules:
    try:
        importlib.import_module(module)
        print(f"  [ok]      {label}")
    except ImportError:
        print(f"  [MISSING] {label}")
        missing.append(label)

connection = sqlite3.connect(":memory:")
try:
    connection.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
    print("  [ok]      SQLite FTS5 support")
except sqlite3.OperationalError:
    print("  [MISSING] SQLite FTS5 support")
    missing.append("SQLite FTS5")
finally:
    connection.close()

if missing:
    print("\nSetup incomplete. Missing: " + ", ".join(missing))
    sys.exit(1)
PYCHECK

# ---------------------------------------------------------------------------
# 7. Tests
# ---------------------------------------------------------------------------
say ""
rule
say "Running the unit tests (synthetic fixtures only -- no real documents)"
rule
if "${VENV_PY}" -m pytest "${PROJECT_ROOT}/tests" -q; then
    say ""
    ok "All tests passed."
else
    say ""
    bad "Tests failed. Do NOT run this against the production until they pass."
    exit 1
fi

# ---------------------------------------------------------------------------
# 8. Next steps
# ---------------------------------------------------------------------------
say ""
rule
say "Setup complete"
rule
say ""
say "Activate the environment:"
say "    source ${VENV_DIR}/bin/activate"
say ""
say "Find your Google Drive production folder:"
say "    ${VENV_PY} -m src.cli locate"
say ""
say "Then run Phase 1 (structural inventory only -- no content is read):"
say "    ./scripts/run_phase1_mac.sh \"/Users/YOU/Library/CloudStorage/GoogleDrive-ACCOUNT/My Drive/Wilson-Rode File\""
say ""
say "The source folder is never modified. All output goes to a sibling folder"
say "named Wilson_Rode_Derived_Index."
say ""
