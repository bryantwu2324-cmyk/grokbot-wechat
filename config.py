"""Local configuration.

Secrets are read only from the process environment or from
``$BRIDGE_DATA_DIR/webhook.env`` when that file is mode 0600.
This module does not read Cursor/Grok app settings, cookies, or databases.
"""
import json, os, stat, tempfile

CODE_DIR = os.path.dirname(os.path.abspath(__file__))
API_ORIGIN = "https://ilinkai.weixin.qq.com"
CDN_ORIGIN = "https://novac2c.cdn.weixin.qq.com"
WEBHOOK_ORIGIN = "https://api2.cursor.sh"
BRIDGE_VERSION = "1.0.0"
BOT_AGENT = "GrokWechatBridge/" + BRIDGE_VERSION
# Official client keeps a QR login session for this long. The protocol does not
# publish a separate server TTL; the server may return status "expired" sooner.
QR_SESSION_TTL_S = 5 * 60
PAUSE_ON_MINUS_14_S = 60 * 60

_PRIVATE_KEYS = (
    "WECHAT_WEBHOOK_URL",
    "WECHAT_WEBHOOK_KEY",
    "WECHAT_FORWARD_ENABLED",
    "WECHAT_SEND_ENABLED",
    "WECHAT_INCLUDE_HISTORY",
    "OWNER_NAME",
    "BOT_NAME",
    "HISTORY_TZ",
    "BATCH_QUIET_S",
    "BATCH_CAP_S",
)

def _default_data_dir():
    return os.path.abspath(os.path.expanduser(os.environ.get("BRIDGE_DATA_DIR", "").strip() or "~/.grokbot-wechat"))

DATA_DIR = _default_data_dir()
CONFIG_ERRORS = []
_FILE_VALUES = {}


def data_dir_problem():
    real = os.path.realpath(DATA_DIR)
    code = os.path.realpath(CODE_DIR)
    if real == code or real.startswith(code + os.sep):
        return "BRIDGE_DATA_DIR must be outside the install directory so credentials are not stored next to the program"
    return None


def ensure_data_dir():
    problem = data_dir_problem()
    if problem:
        raise SystemExit(problem)
    os.makedirs(DATA_DIR, exist_ok=True)
    os.chmod(DATA_DIR, 0o700)
    mode = os.stat(DATA_DIR).st_mode
    if mode & 0o077:
        raise SystemExit("data directory mode is not 0700: %s" % DATA_DIR)
    return DATA_DIR


def mode_is_private(path):
    return not (os.stat(path).st_mode & 0o077)


def refresh():
    """Reload webhook.env. A file that is not mode 0600 is not read."""
    global _FILE_VALUES, CONFIG_ERRORS
    _FILE_VALUES = {}
    CONFIG_ERRORS = []
    path = os.path.join(DATA_DIR, "webhook.env")
    if not os.path.exists(path):
        return
    if not mode_is_private(path):
        CONFIG_ERRORS.append("webhook.env mode is not 0600; refusing to read it")
        return
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if key in _PRIVATE_KEYS:
                    _FILE_VALUES[key] = value
    except OSError:
        CONFIG_ERRORS.append("webhook.env could not be read")


def get(name, default=""):
    refresh()
    if name in os.environ:
        return os.environ.get(name, "").strip()
    return _FILE_VALUES.get(name, default).strip()


def flag(name):
    """Only the exact value 1 turns a switch on."""
    return get(name, "0") == "1"


def forward_enabled():
    return flag("WECHAT_FORWARD_ENABLED")


def send_enabled():
    return flag("WECHAT_SEND_ENABLED")


def include_history():
    # Conversation context goes only to this user's own Grok Bot routine.
    # Set WECHAT_INCLUDE_HISTORY=0 to omit it. Unset means include.
    return get("WECHAT_INCLUDE_HISTORY", "1") != "0"


def webhook_url():
    return get("WECHAT_WEBHOOK_URL")


def webhook_key():
    return get("WECHAT_WEBHOOK_KEY")


def owner_name():
    return get("OWNER_NAME", "User") or "User"


def bot_name():
    return get("BOT_NAME", "grok") or "grok"


def history_tz():
    return get("HISTORY_TZ", "Asia/Shanghai") or "Asia/Shanghai"


def batch_quiet_s():
    try:
        return float(get("BATCH_QUIET_S", "3") or "3")
    except ValueError:
        return 3.0


def batch_cap_s():
    try:
        return float(get("BATCH_CAP_S", "60") or "60")
    except ValueError:
        return 60.0


def atomic_write(path, text, mode=0o600):
    ensure_data_dir()
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    os.chmod(directory, 0o700)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        os.chmod(path, mode)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if not mode_is_private(path):
        raise SystemExit("refusing to leave %s with a mode other than 0600" % os.path.basename(path))


def atomic_json(path, obj):
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def privatize(path):
    if os.path.exists(path):
        os.chmod(path, 0o600)
