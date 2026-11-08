#!/bin/bash
# Shared paths for the box scripts. Secrets are not printed.
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
export BRIDGE_DATA_DIR="${BRIDGE_DATA_DIR:-$HOME/.grokbot-wechat}"
if [ -x "$ROOT/venv/bin/python3" ]; then
  PY="$ROOT/venv/bin/python3"
else
  PY="$(command -v python3)"
fi
