#!/bin/bash
# Start message listening only when WECHAT_FORWARD_ENABLED=1.
# Does not enable sending and does not schedule anything.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/boxlib.sh"
mkdir -p "$BRIDGE_DATA_DIR"
chmod 700 "$BRIDGE_DATA_DIR"
PIDFILE="$BRIDGE_DATA_DIR/forward.pid"
if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
    cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    case "$cmd" in
      *forward.py*) echo "already running pid=$pid"; exit 1 ;;
    esac
  fi
fi
if ! "$PY" "$ROOT/forward.py" --require-forward; then
  echo "not started"
  exit 2
fi
nohup setsid "$PY" -u "$ROOT/forward.py" >> "$BRIDGE_DATA_DIR/forward.out" 2>&1 < /dev/null &
echo $! > "$PIDFILE"
chmod 600 "$PIDFILE" || true
if [ -f "$BRIDGE_DATA_DIR/forward.out" ]; then
  chmod 600 "$BRIDGE_DATA_DIR/forward.out" || true
fi
echo "started pid=$!"
echo "Listening can run. Sending stays off unless WECHAT_SEND_ENABLED=1."
echo "This process does not send on a timer."
