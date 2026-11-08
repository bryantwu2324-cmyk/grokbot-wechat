"""Minimal client for the public WeChat iLink bot HTTP API.

The wire format follows Tencent's published protocol:
https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol_zh_CN.md

This process does not install or impersonate the upstream channel package.
``iLink-App-Id: bot`` is the app id that protocol assigns to this API.
The observation name sent on the wire is GrokWechatBridge/<version>.
"""
import json, os, secrets, socket, urllib.error, urllib.parse, urllib.request
import config

CRED = os.path.join(config.DATA_DIR, "credentials.json")
STATE = os.path.join(config.DATA_DIR, "state.json")
QR_SESSION = os.path.join(config.DATA_DIR, "qr_session.json")


class IlinkError(Exception):
    pass


def encode_client_version(version):
    """Encode major.minor.patch as 0x00MMNNPP, matching the published client."""
    parts = []
    for piece in str(version).split(".")[:3]:
        parts.append(int(piece) if piece.isdigit() else 0)
    while len(parts) < 3:
        parts.append(0)
    major, minor, patch = parts
    return ((major & 0xFF) << 16) | ((minor & 0xFF) << 8) | (patch & 0xFF)


CLIENT_VERSION = str(encode_client_version(config.BRIDGE_VERSION))


def base_info():
    return {"channel_version": config.BRIDGE_VERSION, "bot_agent": config.BOT_AGENT}


def weixin_host_allowed(host):
    if not isinstance(host, str):
        return False
    if host != host.strip() or not host or host.endswith(".") or ":" in host or "/" in host:
        return False
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        return False
    host = host.lower()
    labels = host.split(".")
    for label in labels:
        if not label or label.startswith("-") or label.endswith("-"):
            return False
        if not all(ch.isalnum() or ch == "-" for ch in label):
            return False
    return host == "weixin.qq.com" or host.endswith(".weixin.qq.com")


def _split_https(url):
    if not isinstance(url, str) or not url:
        raise IlinkError("url missing")
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme != "https" or parts.username or parts.password or parts.fragment:
        raise IlinkError("only https URLs without userinfo are allowed")
    if parts.port not in (None, 443):
        raise IlinkError("only port 443 is allowed")
    host = parts.hostname
    if not host:
        raise IlinkError("url host missing")
    return parts, host


def validate_baseurl(url):
    parts, host = _split_https(url)
    if not weixin_host_allowed(host):
        raise IlinkError("api host is not an official weixin.qq.com host")
    if parts.path not in ("", "/") or parts.query:
        raise IlinkError("api base URL must not include a path or query")
    return "https://" + host


def validate_redirect_host(host):
    if not weixin_host_allowed(host):
        raise IlinkError("QR redirect host is not an official weixin.qq.com host; stopped")
    return "https://" + host.lower()


def validate_cdn_url(url):
    parts, host = _split_https(url)
    if not weixin_host_allowed(host):
        raise IlinkError("media host is not an official weixin.qq.com host")
    return urllib.parse.urlunsplit(("https", host, parts.path or "/", parts.query, ""))


def validate_webhook_url(url):
    parts, host = _split_https(url)
    if host != "api2.cursor.sh":
        raise IlinkError("webhook host must be api2.cursor.sh")
    if parts.query:
        raise IlinkError("webhook URL must not include a query string")
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) != 3 or segments[0] != "automations" or segments[1] != "webhook":
        raise IlinkError("webhook path must be /automations/webhook/<id>")
    ident = segments[2]
    if not ident or len(ident) > 200 or any(not (ch.isalnum() or ch in "_-") for ch in ident):
        raise IlinkError("webhook id has unexpected characters")
    return "https://api2.cursor.sh/automations/webhook/" + ident


def common_headers():
    return {
        "iLink-App-Id": "bot",
        "iLink-App-ClientVersion": CLIENT_VERSION,
    }


def x_wechat_uin():
    # Protocol: random uint32, decimal string, then base64.
    import base64
    return base64.b64encode(str(secrets.randbits(32)).encode("ascii")).decode("ascii")


def qr_get_headers():
    """Status polling: app headers only. No Authorization and no UIN."""
    return common_headers()


def qr_post_headers():
    """get_bot_qrcode uses JSON headers and UIN, and does not send a token or base_info."""
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": x_wechat_uin(),
    }
    headers.update(common_headers())
    return headers


def auth_headers(token):
    headers = qr_post_headers()
    headers["Authorization"] = "Bearer " + token.strip()
    return headers


class CdnRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            validate_cdn_url(newurl)
        except IlinkError:
            return None
        return urllib.request.HTTPRedirectHandler.redirect_request(self, req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_opener(*handlers):
    """Direct connection. Environment proxies are ignored so the bot token
    and webhook key are not sent to a third-party proxy."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), *handlers)


def urlopen(req, timeout, opener):
    return opener.open(req, timeout=timeout)


def request(url, *, method="GET", headers=None, body=None, timeout=15, redirects="none"):
    if redirects == "cdn":
        opener = build_opener(CdnRedirect)
    else:
        opener = build_opener(NoRedirect)
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout, opener) as response:
            payload = response.read()
            status = getattr(response, "status", None) or response.getcode()
            return status, payload
    except urllib.error.HTTPError as exc:
        raise IlinkError("http %s" % exc.code) from None
    except (socket.timeout, TimeoutError):
        raise
    except IlinkError:
        raise
    except Exception:
        raise IlinkError("transport failure") from None


def request_json(url, *, method="GET", headers=None, body=None, timeout=15):
    status, payload = request(url, method=method, headers=headers, body=body, timeout=timeout, redirects="none")
    if status != 200:
        raise IlinkError("http %s" % status)
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise IlinkError("response was not json") from None
    if not isinstance(parsed, dict):
        raise IlinkError("response was not a json object")
    return parsed


def load_creds():
    if not os.path.exists(CRED):
        raise IlinkError("credentials.json is missing")
    if not config.mode_is_private(CRED):
        raise IlinkError("credentials.json mode is not 0600; refusing to read it")
    try:
        with open(CRED, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        raise IlinkError("credentials.json is unreadable") from None
    if not isinstance(data, dict):
        raise IlinkError("credentials.json is not an object")
    token = str(data.get("bot_token") or "").strip()
    owner = str(data.get("ilink_user_id") or "").strip()
    bot = str(data.get("ilink_bot_id") or "").strip()
    if not token or not owner or not bot:
        raise IlinkError("credentials.json is missing bot_token, ilink_user_id, or ilink_bot_id")
    baseurl = validate_baseurl(data.get("baseurl") or config.API_ORIGIN)
    return {"baseurl": baseurl, "bot_token": token, "ilink_user_id": owner, "ilink_bot_id": bot}


def load_state():
    if not os.path.exists(STATE):
        return {}
    if not config.mode_is_private(STATE):
        raise IlinkError("state.json mode is not 0600; refusing to read it")
    try:
        with open(STATE, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state):
    config.atomic_json(STATE, state)


def save_creds(data):
    baseurl = validate_baseurl(data.get("baseurl") or config.API_ORIGIN)
    token = str(data.get("bot_token") or "").strip()
    owner = str(data.get("ilink_user_id") or "").strip()
    bot = str(data.get("ilink_bot_id") or "").strip()
    if not token or not owner or not bot:
        raise IlinkError("login response did not include the required credential fields")
    config.atomic_json(CRED, {
        "baseurl": baseurl,
        "bot_token": token,
        "ilink_bot_id": bot,
        "ilink_user_id": owner,
    })


def post(endpoint, body, timeout=15):
    creds = load_creds()
    url = creds["baseurl"].rstrip("/") + "/" + endpoint.lstrip("/")
    payload = dict(body)
    payload["base_info"] = base_info()
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    status, response = request(
        url, method="POST", headers=auth_headers(creds["bot_token"]), body=raw,
        timeout=timeout, redirects="none",
    )
    if status != 200:
        raise IlinkError("http %s" % status)
    return response.decode("utf-8", errors="replace")


def business_ok(raw):
    """HTTP 200 is not enough. A non-zero ret or errcode is a refusal."""
    try:
        parsed = json.loads(raw) if str(raw).strip() else None
    except json.JSONDecodeError:
        return False, None
    if not isinstance(parsed, dict):
        return False, None
    ret = parsed.get("ret")
    errcode = parsed.get("errcode")
    if ret not in (None, 0) or errcode not in (None, 0):
        return False, parsed
    return True, parsed


def send_text(text, context_token=None):
    """Send one text to the bound owner. There is no recipient argument."""
    creds = load_creds()
    state = load_state()
    owner = creds["ilink_user_id"]
    if context_token is None:
        context_token = (state.get("context_tokens") or {}).get(owner) or ""
    message = {
        "from_user_id": "",
        "to_user_id": owner,
        "client_id": "grokwechat-" + secrets.token_hex(8),
        "message_type": 2,
        "message_state": 2,
        "item_list": [{"type": 1, "text_item": {"text": text}}],
    }
    if context_token:
        message["context_token"] = context_token
    raw = post("ilink/bot/sendmessage", {"msg": message}, timeout=15)
    ok, parsed = business_ok(raw)
    code = None if not isinstance(parsed, dict) else parsed.get("ret", parsed.get("errcode"))
    return ok, code


def notify(kind):
    endpoint = "ilink/bot/msg/notifystart" if kind == "start" else "ilink/bot/msg/notifystop"
    try:
        raw = post(endpoint, {}, timeout=10)
    except (IlinkError, socket.timeout, TimeoutError):
        return False
    ok, _parsed = business_ok(raw)
    return ok


def redact(value):
    text = str(value or "")
    if len(text) <= 6:
        return "***"
    return text[:2] + "…" + text[-2:]
