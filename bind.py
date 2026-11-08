#!/usr/bin/env python3
"""Login only. This does not poll messages and does not send messages.

--qr-only   fetch one QR and exit
--wait      poll that QR until confirmed, expired, or the 5 minute client limit
"""
import json, os, sys, time, urllib.parse
import config
import ilink

QR_PNG = os.path.join(config.DATA_DIR, "qr.png")
QR_URL = os.path.join(config.DATA_DIR, "qr_url.txt")
VERIFY = os.path.join(config.DATA_DIR, "verify_code.txt")


def write_qr_png(content, path):
    import qrcode
    image = qrcode.QRCode(box_size=10, border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    image.add_data(content)
    image.make(fit=True)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    image.make_image().save(tmp)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def fetch_qr(http=None):
    http = http or ilink.request_json
    url = config.API_ORIGIN + "/ilink/bot/get_bot_qrcode?bot_type=3"
    body = json.dumps({"local_token_list": []}).encode("utf-8")
    parsed = http(url, method="POST", headers=ilink.qr_post_headers(), body=body, timeout=15)
    qrcode = parsed.get("qrcode")
    content = parsed.get("qrcode_img_content")
    if not qrcode or not content:
        raise ilink.IlinkError("QR response did not include qrcode and qrcode_img_content")
    return {"qrcode": qrcode, "qrcode_img_content": content, "baseurl": config.API_ORIGIN, "started_at": time.time()}


def save_session(session):
    config.atomic_json(ilink.QR_SESSION, session)
    config.atomic_write(QR_URL, session["qrcode_img_content"] + "\n")
    write_qr_png(session["qrcode_img_content"], QR_PNG)


def load_session():
    if not os.path.exists(ilink.QR_SESSION):
        raise ilink.IlinkError("no QR session; run login-qr first")
    if not config.mode_is_private(ilink.QR_SESSION):
        raise ilink.IlinkError("qr_session.json mode is not 0600; refusing to read it")
    with open(ilink.QR_SESSION, encoding="utf-8") as fh:
        session = json.load(fh)
    if not isinstance(session, dict) or not session.get("qrcode"):
        raise ilink.IlinkError("QR session is incomplete")
    return session


def session_age(session, clock):
    try:
        started = float(session.get("started_at") or 0)
    except (TypeError, ValueError):
        started = 0
    return clock() - started


def clear_qr_files():
    for path in (ilink.QR_SESSION, QR_PNG, QR_URL, VERIFY):
        try:
            os.remove(path)
        except OSError:
            pass


def read_verify_code():
    if not os.path.exists(VERIFY):
        return None
    if not config.mode_is_private(VERIFY):
        raise ilink.IlinkError("verify_code.txt mode is not 0600; refusing to read it")
    with open(VERIFY, encoding="utf-8") as fh:
        code = fh.read().strip()
    try:
        os.remove(VERIFY)
    except OSError:
        pass
    return code or None


def qr_only(http=None):
    config.ensure_data_dir()
    session = fetch_qr(http=http)
    save_session(session)
    print("QR image: %s" % QR_PNG)
    print("QR link file: %s" % QR_URL)
    print("Scan with the WeChat account that will be the only allowed sender.")
    print("Message listening was not started. Sending was not started.")
    print("Client session limit: %d seconds. The server may return expired sooner." % config.QR_SESSION_TTL_S)
    print("Do not paste the QR link into chat, logs, or git. After scanning, run login-wait.")
    return 0


def wait_for_scan(http=None, clock=None, sleeper=None, input_code=None):
    http = http or ilink.request_json
    clock = clock or time.time
    sleeper = sleeper or time.sleep
    input_code = input_code or read_verify_code
    session = load_session()
    if session_age(session, clock) >= config.QR_SESSION_TTL_S:
        clear_qr_files()
        print("QR session is older than %d seconds. Run login-qr again." % config.QR_SESSION_TTL_S)
        return 4
    base = ilink.validate_baseurl(session.get("baseurl") or config.API_ORIGIN)
    verify = None
    while session_age(session, clock) < config.QR_SESSION_TTL_S:
        url = base + "/ilink/bot/get_qrcode_status?qrcode=" + urllib.parse.quote(str(session["qrcode"]))
        if verify:
            url += "&verify_code=" + urllib.parse.quote(verify)
        try:
            parsed = http(url, method="GET", headers=ilink.qr_get_headers(), timeout=35)
        except (ilink.IlinkError, TimeoutError):
            parsed = {"status": "wait"}
        status = parsed.get("status")
        if status == "confirmed":
            baseurl = parsed.get("baseurl") or base
            ilink.save_creds({
                "baseurl": baseurl,
                "bot_token": parsed.get("bot_token"),
                "ilink_bot_id": parsed.get("ilink_bot_id"),
                "ilink_user_id": parsed.get("ilink_user_id"),
            })
            clear_qr_files()
            print("Login saved: %s" % ilink.CRED)
            print("mode 0600. token was not printed. owner %s" % ilink.redact(parsed.get("ilink_user_id")))
            print("Message listening was not started. Sending was not started.")
            return 0
        if status == "binded_redirect":
            clear_qr_files()
            print("Server returned binded_redirect and did not issue credentials.")
            print("This bridge did not mark the account as connected and did not save a token.")
            return 3
        if status == "scaned_but_redirect":
            host = parsed.get("redirect_host")
            if not host:
                print("Redirect status had no host. Stopped.")
                return 5
            base = ilink.validate_redirect_host(host)
            session["baseurl"] = base
            config.atomic_json(ilink.QR_SESSION, session)
            print("QR status moved to an official WeChat host. Continuing to wait.")
            continue
        if status == "need_verifycode":
            print("The phone is showing a number. Write it to %s with mode 0600." % VERIFY)
            deadline = float(session["started_at"]) + config.QR_SESSION_TTL_S
            while clock() < deadline:
                code = input_code()
                if code:
                    verify = code
                    break
                sleeper(1)
            else:
                clear_qr_files()
                print("QR session reached the client limit before a verify code was read.")
                return 4
            continue
        if status in ("expired", "verify_code_blocked"):
            clear_qr_files()
            print("QR status is %s. This command does not refresh it in the background. Run login-qr again." % status)
            return 4
        if status not in ("wait", "scaned", None):
            print("Unhandled QR status. Stopped without saving credentials.")
            return 5
        sleeper(1)
    clear_qr_files()
    print("QR session reached the %d second client limit. Run login-qr again." % config.QR_SESSION_TTL_S)
    return 4


def run(argv):
    if "--qr-only" in argv:
        try:
            return qr_only()
        except (ilink.IlinkError, OSError) as exc:
            print("QR was not created: %s" % exc)
            return 1
    if "--wait" in argv:
        try:
            return wait_for_scan()
        except (ilink.IlinkError, OSError) as exc:
            print("Login did not finish: %s" % exc)
            return 1
    print("Usage: bind.py --qr-only | --wait")
    print("Neither command starts message listening or sending.")
    print("QR client limit: %d seconds. Credentials directory: %s" % (config.QR_SESSION_TTL_S, config.DATA_DIR))
    return 2


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
