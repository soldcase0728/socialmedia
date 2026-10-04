#!/bin/bash
# Install the Scrapling MCP server in Claude Code on the web sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

if ! command -v scrapling >/dev/null 2>&1; then
  uv tool install "scrapling[ai]"
fi
