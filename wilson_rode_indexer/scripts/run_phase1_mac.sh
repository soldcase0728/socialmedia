#!/usr/bin/env bash
#
# Run Phase 1 (structural inventory) against a Google Drive-synced production
# folder on macOS.
#
# Phase 1 reads structural facts only: filename, path, size, timestamps,
# SHA-256, PDF page count, encryption state, readability. It does NOT read
# substantive document content, does NOT extract text, and does NOT OCR.
#
# Usage:
#   ./scripts/run_phase1_mac.sh "/Users/Todd/Library/CloudStorage/GoogleDrive-ACCOUNT/My Drive/Wilson-Rode File"
#
# Options (after the source path):
#   --output DIR              Override the derived-index folder
#   --workers N               Override the worker count
#   --limit N                 Process at most N new files (smoke test)
#   --force                   Re-probe every file even if unchanged
#   --no-progress             Disable progress bars
#   --allow-writable-source   Acknowledge a writable source and proceed anyway
#
# The script REFUSES to run when:
#   1. the source folder does not exist
#   2. the source folder is writable by this application
#   3. the source folder and the output folder are the same
#   4. the source folder contains no PDFs
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${PROJECT_ROOT}/.venv/bin/python"
OUTPUT_DIR=""
ALLOW_WRITABLE=0
# The CLI takes some options before the subcommand and some after it, so the
# two groups are collected separately rather than in one list.
GLOBAL_ARGS=()
PHASE_ARGS=()

die() {
    printf '\n' >&2
    printf 'REFUSING TO RUN: %s\n' "$1" >&2
    shift
    while [[ $# -gt 0 ]]; do
        printf '  %s\n' "$1" >&2
        shift
    done
    printf '\nNothing was read, written, or modified.\n\n' >&2
    exit 1
}

# ---------------------------------------------------------------------------
# Argument parsing -- the source path is required and must be quoted
# ---------------------------------------------------------------------------
if [[ $# -lt 1 ]]; then
    printf '\nUsage:\n' >&2
    printf '  %s "SOURCE_FOLDER" [options]\n\n' "$0" >&2
    printf 'Example:\n' >&2
    printf '  %s "/Users/Todd/Library/CloudStorage/GoogleDrive-ACCOUNT/My Drive/Wilson-Rode File"\n\n' "$0" >&2
    printf 'The path MUST be quoted: it contains spaces and a hyphen.\n' >&2
    printf 'Run `python -m src.cli locate` if you do not know the path.\n\n' >&2
    exit 2
fi

SOURCE_DIR="$1"
shift

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            OUTPUT_DIR="${2:-}"
            shift 2
            ;;
        --allow-writable-source)
            ALLOW_WRITABLE=1
            shift
            ;;
        --workers)
            GLOBAL_ARGS+=("$1" "${2:-}")
            shift 2
            ;;
        --no-progress|--quiet)
            GLOBAL_ARGS+=("$1")
            shift
            ;;
        --limit)
            PHASE_ARGS+=("$1" "${2:-}")
            shift 2
            ;;
        --force|--no-reports)
            PHASE_ARGS+=("$1")
            shift
            ;;
        -h|--help)
            sed -n '2,28p' "${BASH_SOURCE[0]}"
            exit 0
            ;;
        *)
            die "Unknown option: $1" "Run with --help for usage."
            ;;
    esac
done

printf '\n'
printf '==================================================================\n'
printf 'Wilson-Rode derived index -- Phase 1 pre-flight checks\n'
printf '==================================================================\n'

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
if [[ ! -x "${VENV_PY}" ]]; then
    die "The virtual environment is missing." \
        "Expected: ${VENV_PY}" \
        "Run ./scripts/setup_mac.sh first."
fi
printf '  [ok] virtual environment    %s\n' "${VENV_PY}"

# ---------------------------------------------------------------------------
# Check 1: the source folder must exist and be a readable directory
# ---------------------------------------------------------------------------
if [[ ! -e "${SOURCE_DIR}" ]]; then
    die "The source folder does not exist." \
        "Path given: ${SOURCE_DIR}" \
        "" \
        "If this is a Google Drive path, confirm Google Drive is running and" \
        "the folder is synced. Run \`python -m src.cli locate\` to search for it." \
        "Remember to quote the path -- it contains spaces."
fi
if [[ ! -d "${SOURCE_DIR}" ]]; then
    die "The source path exists but is not a directory." \
        "Path given: ${SOURCE_DIR}"
fi
if [[ ! -r "${SOURCE_DIR}" ]]; then
    die "The source folder is not readable by this user." \
        "Path given: ${SOURCE_DIR}" \
        "Grant your Terminal Full Disk Access in System Settings >" \
        "Privacy & Security, then try again."
fi

SOURCE_ABS="$(cd "${SOURCE_DIR}" && pwd -P)"
printf '  [ok] source exists          %s\n' "${SOURCE_ABS}"

# ---------------------------------------------------------------------------
# Check 3 (resolved early, needed for the same-folder comparison)
# ---------------------------------------------------------------------------
if [[ -z "${OUTPUT_DIR}" ]]; then
    OUTPUT_DIR="$(dirname "${SOURCE_ABS}")/Wilson_Rode_Derived_Index"
fi

# Resolve the output path WITHOUT creating it: creating a directory before
# checking whether it sits inside the production would itself be a write to
# the source folder.
if [[ -d "${OUTPUT_DIR}" ]]; then
    OUTPUT_ABS="$(cd "${OUTPUT_DIR}" && pwd -P)"
else
    OUTPUT_PARENT="$(dirname "${OUTPUT_DIR}")"
    if [[ -d "${OUTPUT_PARENT}" ]]; then
        OUTPUT_ABS="$(cd "${OUTPUT_PARENT}" && pwd -P)/$(basename "${OUTPUT_DIR}")"
    else
        OUTPUT_ABS="${OUTPUT_DIR}"
    fi
fi

if [[ "${SOURCE_ABS}" == "${OUTPUT_ABS}" ]]; then
    die "The source folder and the output folder are the same." \
        "Source: ${SOURCE_ABS}" \
        "Output: ${OUTPUT_ABS}" \
        "" \
        "The derived index must never be written inside the production."
fi
case "${OUTPUT_ABS}/" in
    "${SOURCE_ABS}/"*)
        die "The output folder is inside the source folder." \
            "Source: ${SOURCE_ABS}" \
            "Output: ${OUTPUT_ABS}" \
            "" \
            "Choose an output folder outside the production, or omit --output" \
            "to use the default sibling folder."
        ;;
esac
# Only now, having confirmed it is outside the production, create it.
mkdir -p "${OUTPUT_ABS}"
printf '  [ok] output is separate     %s\n' "${OUTPUT_ABS}"

# ---------------------------------------------------------------------------
# Check 2: the source folder must NOT be writable by this application
# ---------------------------------------------------------------------------
WRITE_PROBE="${SOURCE_ABS}/.wri_write_probe_$$"
SOURCE_WRITABLE=0
if ( : > "${WRITE_PROBE}" ) 2>/dev/null; then
    SOURCE_WRITABLE=1
    rm -f "${WRITE_PROBE}" 2>/dev/null || true
fi

if [[ "${SOURCE_WRITABLE}" -eq 1 ]]; then
    if [[ "${ALLOW_WRITABLE}" -eq 0 ]]; then
        die "The source folder is writable by this application." \
            "Source: ${SOURCE_ABS}" \
            "" \
            "The production must be treated as read-only. While this process" \
            "never writes to it, an operating-system level guarantee is" \
            "stronger than a promise in code." \
            "" \
            "Recommended -- make the folder read-only, then re-run:" \
            "    chmod -R a-w \"${SOURCE_ABS}\"" \
            "" \
            "To restore write access afterwards:" \
            "    chmod -R u+w \"${SOURCE_ABS}\"" \
            "" \
            "Note: Google Drive may reset permissions on re-sync, and some" \
            "Drive configurations do not honour chmod at all. If you cannot" \
            "make the folder read-only, an alternative is to work from a" \
            "read-only copy on a separate volume." \
            "" \
            "Also note: do NOT run this as root or with sudo. The root user" \
            "bypasses permission bits, so this check can never pass for it." \
            "" \
            "If you accept the risk and want to proceed against a writable" \
            "source, re-run with --allow-writable-source. That flag only" \
            "suppresses this check; the application still never writes to the" \
            "source, and the in-code read-only guard remains active."
    fi
    printf '  [!!] source is WRITABLE     proceeding under --allow-writable-source\n'
    printf '       The application still will not write to it, but the OS is\n'
    printf '       not enforcing that for you.\n'
else
    printf '  [ok] source is read-only    write probe refused by the OS\n'
fi

# ---------------------------------------------------------------------------
# Check 4: the source folder must contain at least one PDF
# ---------------------------------------------------------------------------
printf '  [..] counting PDFs (this can take a moment on a large folder)\n'
PDF_COUNT="$(find "${SOURCE_ABS}" -type f -iname '*.pdf' -print 2>/dev/null | head -n 200000 | wc -l | tr -d ' ')"

if [[ "${PDF_COUNT}" -eq 0 ]]; then
    die "The source folder contains no PDF files." \
        "Source: ${SOURCE_ABS}" \
        "" \
        "Either this is the wrong folder, or Google Drive has not downloaded" \
        "the files yet. In Finder, right-click the folder and choose" \
        "'Make available offline', wait for the download to finish, then" \
        "re-run this script."
fi
printf '  [ok] PDFs found             %s\n' "${PDF_COUNT}"

# ---------------------------------------------------------------------------
# All checks passed
# ---------------------------------------------------------------------------
printf '==================================================================\n'
printf 'All pre-flight checks passed. Starting Phase 1.\n'
printf '\n'
printf '  Phase 1 reads STRUCTURAL FACTS ONLY.\n'
printf '  It does not read document content, extract text, or run OCR.\n'
printf '  It stops after writing the Phase 1 reports.\n'
printf '==================================================================\n'
printf '\n'

cd "${PROJECT_ROOT}"
exec "${VENV_PY}" -m src.cli \
    --source "${SOURCE_ABS}" \
    --output "${OUTPUT_ABS}" \
    "${GLOBAL_ARGS[@]+"${GLOBAL_ARGS[@]}"}" \
    phase1 \
    "${PHASE_ARGS[@]+"${PHASE_ARGS[@]}"}"
