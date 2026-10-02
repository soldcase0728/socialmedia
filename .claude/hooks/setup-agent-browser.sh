#!/usr/bin/env bash
# Installs and configures agent-browser (https://github.com/vercel-labs/agent-browser)
# for Claude Code on the web sessions. Idempotent; no-op on local machines.
set -euo pipefail

[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0

AGENT_BROWSER_VERSION="0.38.2"

if ! agent-browser --version 2>/dev/null | grep -q "$AGENT_BROWSER_VERSION"; then
  npm install -g --silent "agent-browser@${AGENT_BROWSER_VERSION}" >/dev/null 2>&1
fi

# certutil is needed to trust the session proxy's CA in Chromium's NSS store.
if ! command -v certutil >/dev/null 2>&1; then
  (apt-get install -y -qq libnss3-tools || (apt-get update -qq && apt-get install -y -qq libnss3-tools)) >/dev/null 2>&1
fi

# Reuse the pre-installed Playwright Chromium instead of `agent-browser install`.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  [ -x /opt/pw-browsers/chromium ] && echo "export AGENT_BROWSER_EXECUTABLE_PATH=/opt/pw-browsers/chromium" >> "$CLAUDE_ENV_FILE"
  [ -f /root/.ccr/ca-bundle.crt ] && echo "export AGENT_BROWSER_CA_CERT=/root/.ccr/ca-bundle.crt" >> "$CLAUDE_ENV_FILE"
fi
