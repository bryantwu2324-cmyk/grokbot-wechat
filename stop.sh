#!/bin/bash
# Stop the listener started by start.sh. Only a process whose command line
# contains forward.py is signalled.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/boxlib.sh"
PIDFILE="$BRIDGE_DATA_DIR/forward.pid"
if [ ! -f "$PIDFILE" ]; then
  echo "not running"
  exit 0
fi
pid="$(cat "$PIDFILE" 2>/dev/null || true)"
if [ -z "${pid:-}" ] || ! kill -0 "$pid" 2>/dev/null; then
  rm -f "$PIDFILE"
  echo "not running"
  exit 0
fi
cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
case "$cmd" in
  *forward.py*) ;;
  *) echo "pid $pid is not forward.py; not killing"; exit 1 ;;
esac
kill -TERM "$pid"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  kill -0 "$pid" 2>/dev/null || break
  sleep 1
done
if kill -0 "$pid" 2>/dev/null; then
  echo "still running pid=$pid"
  exit 1
fi
rm -f "$PIDFILE"
echo "stopped"
