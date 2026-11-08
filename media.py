"""Download and decrypt media that the bound user sent.

Downloads stay on official weixin.qq.com hosts. AES keys and CDN query
parameters are not copied into the webhook payload.
"""
import base64, binascii, os, time, urllib.parse
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import config
import ilink

CDN_BASE = config.CDN_ORIGIN + "/c2c"
TYPE_NAMES = {1: "text", 2: "image", 3: "voice", 4: "file", 5: "video"}
ITEM_KEYS = {1: "text_item", 2: "image_item", 3: "voice_item", 4: "file_item", 5: "video_item"}


def summarize(item):
    """Allowlisted fields only. CDN parameters and AES keys are dropped."""
    if not isinstance(item, dict):
        return {"type": None, "type_name": "unknown"}
    kind = item.get("type")
    summary = {"type": kind, "type_name": TYPE_NAMES.get(kind, "unknown")}
    sub = item.get(ITEM_KEYS.get(kind, ""), {}) or {}
    if not isinstance(sub, dict):
        sub = {}
    if kind == 1:
        summary["text"] = sub.get("text")
    elif kind == 3 and sub.get("text"):
        summary["text"] = sub.get("text")
    elif kind == 4 and sub.get("file_name"):
        summary["file_name"] = os.path.basename(str(sub.get("file_name")))[:200]
    return summary


def parse_key(item_sub):
    hx = item_sub.get("aeskey")
    if hx:
        return binascii.unhexlify(hx)
    encoded = (item_sub.get("media") or {}).get("aes_key")
    if not encoded:
        raise ValueError("no aes key")
    raw = base64.b64decode(encoded)
    if len(raw) == 16:
        return raw
    if len(raw) == 32:
        return binascii.unhexlify(raw.decode())
    raise ValueError("unexpected aes key length")


def media_url(media):
    if not isinstance(media, dict):
        raise ilink.IlinkError("media missing")
    if media.get("full_url"):
        return ilink.validate_cdn_url(media["full_url"])
    query = media.get("encrypt_query_param")
    if not query:
        raise ilink.IlinkError("media url missing")
    return ilink.validate_cdn_url(
        CDN_BASE + "/download?encrypted_query_param=" + urllib.parse.quote(str(query), safe="")
    )


def download(url, timeout=60):
    safe = ilink.validate_cdn_url(url)
    status, payload = ilink.request(
        safe, method="GET",
        headers={"User-Agent": config.BOT_AGENT},
        timeout=timeout, redirects="cdn",
    )
    if status != 200:
        raise ilink.IlinkError("media http %s" % status)
    return payload


def decrypt(data, key):
    dec = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    out = dec.update(data) + dec.finalize()
    pad = out[-1] if out else 0
    if 1 <= pad <= 16 and out.endswith(bytes([pad]) * pad):
        out = out[:-pad]
    return out


MAGIC = (
    (b"\xff\xd8\xff", "jpg"), (b"\x89PNG", "png"), (b"GIF8", "gif"), (b"RIFF", "webp"),
    (b"%PDF", "pdf"), (b"PK\x03\x04", "zip"), (b"#!AMR", "amr"), (b"\x02#!SILK", "silk"),
    (b"#!SILK", "silk"),
)


def sniff_ext(data, default="bin"):
    for magic, ext in MAGIC:
        if data.startswith(magic):
            return ext
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "mp4"
    return default


def _safe_ext(name, fallback):
    cleaned = "".join(ch for ch in str(name or "") if ch.isalnum())[:8]
    return cleaned or fallback


def fetch_item(item, outdir, ts=None):
    kind = item.get("type")
    name = TYPE_NAMES.get(kind, "media")
    sub = item.get(ITEM_KEYS.get(kind, ""), {}) or {}
    if not isinstance(sub, dict):
        raise ilink.IlinkError("media item missing")
    media = sub.get("media") or {}
    try:
        key = parse_key(sub)
    except ValueError:
        key = None
    if key is None and kind != 2:
        raise ilink.IlinkError("media key missing")
    blob = download(media_url(media))
    plain = decrypt(blob, key) if key is not None else blob
    ext = None
    if kind == 4 and sub.get("file_name") and "." in str(sub.get("file_name")):
        ext = _safe_ext(str(sub["file_name"]).rsplit(".", 1)[1], "")
    ext = ext or sniff_ext(plain)
    os.makedirs(outdir, exist_ok=True)
    os.chmod(outdir, 0o700)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(ts or time.time()))
    path = os.path.join(outdir, "%s-%s.%s" % (stamp, name, ext))
    n = 1
    while os.path.exists(path):
        path = os.path.join(outdir, "%s-%s-%d.%s" % (stamp, name, n, ext))
        n += 1
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(plain)
    os.chmod(path, 0o600)
    return os.path.abspath(path)
