#!/bin/bash
# Local status. Does not contact WeChat or Grok Bot.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/boxlib.sh"
"$PY" "$ROOT/forward.py" --check
PIDFILE="$BRIDGE_DATA_DIR/forward.pid"
if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
    echo "process=running pid=$pid"
    exit 0
  fi
fi
echo "process=stopped"
