#!/bin/bash
# Install the local wheels into ./venv and create a private data directory.
# This script does not contact PyPI, does not start listening, and does not send.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
if [ ! -d wheels ] || ! compgen -G "wheels/*.whl" >/dev/null; then
  echo "No vendored wheels in ./wheels."
  echo "Use the box artifact. This installer does not contact PyPI or any other host."
  exit 1
fi
python3 verify_wheels.py
python3 -m venv venv
./venv/bin/pip install --no-index --find-links wheels -r requirements.txt
DATA="${BRIDGE_DATA_DIR:-$HOME/.grokbot-wechat}"
mkdir -p "$DATA"
chmod 700 "$DATA"
if [ ! -f "$DATA/webhook.env" ]; then
  umask 077
  cat > "$DATA/webhook.env" <<'EOF'
# Values come from the official Grok Bot routine panel.
# Do not point this file at Cursor or Grok app settings. Keep mode 0600.
WECHAT_WEBHOOK_URL=
WECHAT_WEBHOOK_KEY=
WECHAT_FORWARD_ENABLED=0
WECHAT_SEND_ENABLED=0
EOF
  chmod 600 "$DATA/webhook.env"
fi
echo "Installed. Forwarding is off. Sending is off."
echo "Data directory: $DATA"
echo "Next: write the webhook URL and key into that webhook.env, then run ./login-qr.sh"
