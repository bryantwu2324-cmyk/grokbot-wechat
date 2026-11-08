#!/usr/bin/env python3
"""Disabled.

A second getUpdates client would consume the cursor the forwarder needs.
This file is not a login command and it does not send.
"""
import sys

print("poll.py is disabled.")
print("Login without listening: ./login-qr.sh then, after the scan, ./login-wait.sh")
print("Listen only after WECHAT_FORWARD_ENABLED=1: ./start.sh")
sys.exit(2)
