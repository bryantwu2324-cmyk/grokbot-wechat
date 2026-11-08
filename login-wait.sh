#!/bin/bash
# Wait for the QR from login-qr.sh to be confirmed. Does not listen or send.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/boxlib.sh"
exec "$PY" "$ROOT/bind.py" --wait
