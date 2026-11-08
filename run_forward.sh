#!/bin/bash
# Foreground listener. Exits immediately unless forwarding is explicitly enabled.
# It does not restart itself and it does not send on a schedule.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/boxlib.sh"
"$PY" "$ROOT/forward.py" --require-forward
exec "$PY" -u "$ROOT/forward.py"
