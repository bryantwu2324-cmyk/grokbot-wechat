#!/usr/bin/env python3
"""Local reply command for the existing Grok Bot boss.

This does not call a model. It sends one text to the bound WeChat user when
sending has been explicitly enabled. It never chooses a different recipient.
"""
import sys
import history
import ilink
import config


def run(argv):
    if "--app" in argv:
        print("proactive send is disabled")
        return 2
    args = [arg for arg in argv if arg != "--no-context"]
    no_context = "--no-context" in argv
    reply_to = None
    text_args = []
    to_override = False
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--reply-to-ms" and index + 1 < len(args):
            try:
                reply_to = int(args[index + 1])
            except ValueError:
                print("reply-to-ms is not an integer")
                return 2
            index += 2
            continue
        if arg == "--to":
            to_override = True
            index += 2
            continue
        if arg.startswith("--"):
            print("unknown argument")
            return 2
        text_args.append(arg)
        index += 1
    if to_override:
        print("recipient override is disabled; replies go only to the bound user")
        return 2
    text = " ".join(text_args).strip()
    if not text:
        print("usage: reply.sh \"text\" --reply-to-ms <trigger_ms>")
        return 2
    if not config.send_enabled():
        print("sending is disabled (WECHAT_SEND_ENABLED is not 1); nothing was sent")
        return 2
    if config.data_dir_problem():
        print(config.data_dir_problem())
        return 2
    try:
        creds = ilink.load_creds()
    except ilink.IlinkError as exc:
        print("not sent: %s" % exc)
        return 2
    if reply_to is not None:
        try:
            state = ilink.load_state()
        except ilink.IlinkError as exc:
            print("not sent: %s" % exc)
            return 2
        last = state.get("last_inbound_ms") or 0
        if last and last > reply_to + 500:
            print("SUPERSEDED: the bound user sent a newer message; nothing was sent")
            return 4
    if len(text) > 16000:
        print("not sent: text is longer than the local 16000 character guard")
        return 2
    try:
        ok, code = ilink.send_text(text, context_token="" if no_context else None)
    except (ilink.IlinkError, TimeoutError, OSError) as exc:
        print("not sent: %s" % exc)
        return 3
    if not ok:
        print("not sent: wechat ret=%s; nothing was queued" % code)
        return 3
    try:
        history.append(history.bot_line(text))
    except OSError:
        pass
    print("sent to %s" % ilink.redact(creds["ilink_user_id"]))
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
