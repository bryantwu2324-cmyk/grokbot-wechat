#!/bin/bash
# Fetch one login QR and exit. Does not listen for messages and does not send.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/boxlib.sh"
exec "$PY" "$ROOT/bind.py" --qr-only
