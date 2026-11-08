"""Local conversation note shipped to this user's own Grok Bot routine."""
import os, time
from datetime import datetime
from zoneinfo import ZoneInfo
import config

HISTORY = os.path.join(config.DATA_DIR, "history.log")
MAX_LINES, KEEP_LINES = 2000, 1000


def clean(value):
    return " / ".join(part.strip() for part in str(value or "").replace("\r\n", "\n").split("\n") if part.strip())


def stamp(ts=None):
    try:
        zone = ZoneInfo(config.history_tz())
    except Exception:
        zone = ZoneInfo("Asia/Shanghai")
    return datetime.fromtimestamp(ts or time.time(), zone).strftime("%Y-%m-%d %H:%M")


def item_text(item):
    kind = item.get("type")
    if kind == 1:
        return clean(item.get("text"))
    path = item.get("file")
    if kind == 2:
        return "[图片 %s]" % path if path else "[图片 下载失败]"
    if kind == 4:
        name = clean(item.get("file_name") or "")
        return "[文件 %s %s]" % (name, path) if path else "[文件 %s 下载失败]" % name
    if kind == 3:
        if item.get("text"):
            return "[语音: %s]" % clean(item.get("text"))
        return "[语音 %s]" % path if path else "[语音 下载失败]"
    if kind == 5:
        return "[视频 %s]" % path if path else "[视频 下载失败]"
    return "[未知类型 %s]" % kind


def user_line(payloads):
    parts = [item_text(item) for payload in payloads for item in payload.get("items", [])]
    ts = (payloads[0].get("create_time_ms") or 0) / 1000 or None
    return "[%s] %s：%s" % (stamp(ts), config.owner_name(), " ".join(part for part in parts if part))


def bot_line(text, ts=None):
    return "[%s] %s：%s" % (stamp(ts), config.bot_name(), clean(text))


def append(line, path=None):
    path = path or HISTORY
    config.ensure_data_dir()
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as fh:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except Exception:
            pass
        fh.seek(0, os.SEEK_END)
        fh.write(line.replace("\n", " / ") + "\n")
        fh.flush()
        fh.seek(0)
        lines = fh.readlines()
        if len(lines) > MAX_LINES:
            fh.seek(0)
            fh.truncate()
            fh.writelines(lines[-KEEP_LINES:])
            fh.flush()
    os.chmod(path, 0o600)


def tail(n=40, path=None):
    path = path or HISTORY
    if os.path.exists(path) and not config.mode_is_private(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            return "".join(fh.readlines()[-n:])
    except FileNotFoundError:
        return ""
    except OSError:
        return ""
