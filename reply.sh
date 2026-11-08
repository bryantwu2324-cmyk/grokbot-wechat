#!/bin/bash
# Local reply command. The Grok Bot boss calls this. It does not call a model.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/boxlib.sh"
exec "$PY" "$ROOT/send.py" "$@"
