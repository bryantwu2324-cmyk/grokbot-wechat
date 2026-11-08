#!/bin/bash
# The old watchdog started the listener and could lead to a scheduled send.
# It is now a no-op so an existing cron entry cannot turn the bridge back on.
echo "watchdog disabled: this bridge does not auto-restart and does not send scheduled messages"
exit 0
