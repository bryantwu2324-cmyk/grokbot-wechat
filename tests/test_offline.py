"""Offline tests. No WeChat login, no webhook delivery, no model call.

Network entry points are replaced with fakes. A passing test is not a live login.
"""
import hashlib, io, json, os, stat, subprocess, sys, tempfile, unittest
from contextlib import redirect_stdout
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="bridge-test-")
os.environ["BRIDGE_DATA_DIR"] = TMP
os.environ["OWNER_NAME"] = "Tester"
os.environ["BOT_NAME"] = "grok"
for _name in (
    "WECHAT_FORWARD_ENABLED", "WECHAT_SEND_ENABLED", "WECHAT_WEBHOOK_URL",
    "WECHAT_WEBHOOK_KEY", "WECHAT_INCLUDE_HISTORY", "https_proxy", "HTTPS_PROXY",
    "http_proxy", "HTTP_PROXY",
):
    os.environ.pop(_name, None)
sys.path.insert(0, ROOT)

import bind, config, forward, history, ilink, media, policy, send  # noqa: E402

OWNER = "owner@im.wechat"
BOT = "bot@im.bot"
WEBHOOK = "https://api2.cursor.sh/automations/webhook/routine_1"


def _private(path, text):
    config.atomic_write(path, text)


class PolicyTest(unittest.TestCase):
    def test_owner_direct_message_is_accepted(self):
        decision, reason = policy.classify(
            {"message_type": 1, "from_user_id": OWNER, "to_user_id": BOT}, OWNER, BOT
        )
        self.assertEqual((decision, reason), ("accept", "owner"))

    def test_stranger_group_and_bot_echo_are_rejected(self):
        cases = [
            {"message_type": 1, "from_user_id": "other@im.wechat", "to_user_id": BOT},
            {"message_type": 1, "from_user_id": OWNER, "to_user_id": BOT, "group_id": "g"},
            {"message_type": 2, "from_user_id": OWNER, "to_user_id": BOT},
            {"message_type": 1, "from_user_id": OWNER, "to_user_id": "someone-else"},
        ]
        reasons = [policy.classify(item, OWNER, BOT)[1] for item in cases]
        self.assertEqual(reasons, ["not-owner", "group", "not-user-message", "unexpected-recipient"])
        decision, reason = policy.classify({"message_type": 1, "from_user_id": OWNER}, OWNER, BOT)
        self.assertEqual((decision, reason), ("accept", "owner"))

    def test_missing_owner_rejects_everything(self):
        decision, reason = policy.classify(
            {"message_type": 1, "from_user_id": OWNER, "to_user_id": BOT}, "", BOT
        )
        self.assertEqual((decision, reason), ("reject", "not-owner"))


class HostTest(unittest.TestCase):
    def test_weixin_hosts(self):
        self.assertTrue(ilink.weixin_host_allowed("ilinkai.weixin.qq.com"))
        self.assertTrue(ilink.weixin_host_allowed("a.b.weixin.qq.com"))
        self.assertFalse(ilink.weixin_host_allowed("weixin.qq.com.evil.com"))
        self.assertFalse(ilink.weixin_host_allowed("evil.com"))
        self.assertFalse(ilink.weixin_host_allowed("127.0.0.1"))
        self.assertFalse(ilink.weixin_host_allowed("ilinkai.weixin.qq.com."))
        self.assertFalse(ilink.weixin_host_allowed("user@ilinkai.weixin.qq.com"))

    def test_webhook_shape(self):
        self.assertEqual(ilink.validate_webhook_url(WEBHOOK), WEBHOOK)
        for bad in (
            "http://api2.cursor.sh/automations/webhook/abc",
            "https://api2.cursor.sh.evil.com/automations/webhook/abc",
            "https://hookdeck.example/automations/webhook/abc",
            "https://api2.cursor.sh/automations/webhook/abc?x=1",
            "https://user:pass@api2.cursor.sh/automations/webhook/abc",
            "https://api2.cursor.sh/automations/webhook/abc/extra",
        ):
            with self.assertRaises(ilink.IlinkError):
                ilink.validate_webhook_url(bad)

    def test_cdn_and_base_urls(self):
        good = "https://novac2c.cdn.weixin.qq.com/c2c/download?encrypted_query_param=abc"
        self.assertTrue(ilink.validate_cdn_url(good).startswith("https://novac2c.cdn.weixin.qq.com/"))
        with self.assertRaises(ilink.IlinkError):
            ilink.validate_cdn_url("https://evil.example/file")
        with self.assertRaises(ilink.IlinkError):
            ilink.validate_cdn_url("http://novac2c.cdn.weixin.qq.com/c2c/download")
        self.assertEqual(ilink.validate_baseurl("https://ilinkai.weixin.qq.com"), "https://ilinkai.weixin.qq.com")
        with self.assertRaises(ilink.IlinkError):
            ilink.validate_baseurl("https://ilinkhub.ai")
        with self.assertRaises(ilink.IlinkError):
            ilink.validate_redirect_host("evil.example")

    def test_direct_opener_ignores_proxy_env(self):
        import urllib.request
        os.environ["https_proxy"] = "http://127.0.0.1:9"
        try:
            opener = ilink.build_opener()
            default = urllib.request.build_opener()
        finally:
            os.environ.pop("https_proxy", None)
        ours = [handler for handler in opener.handlers if isinstance(handler, urllib.request.ProxyHandler)]
        default_proxies = [handler.proxies for handler in default.handlers if isinstance(handler, urllib.request.ProxyHandler)]
        self.assertEqual(ours, [])
        self.assertEqual(default_proxies, [{"https": "http://127.0.0.1:9"}])

    def test_redirects_do_not_leave_weixin_or_carry_the_webhook(self):
        self.assertIsNone(ilink.NoRedirect().redirect_request(None, None, 302, "x", {}, "https://evil.example/a"))
        self.assertIsNone(ilink.CdnRedirect().redirect_request(None, None, 302, "x", {}, "https://evil.example/a"))
        allowed = ilink.CdnRedirect().redirect_request(
            urllib_request("https://novac2c.cdn.weixin.qq.com/c2c/download"),
            None, 302, "x", {}, "https://novac2c.cdn.weixin.qq.com/c2c/other",
        )
        self.assertIsNotNone(allowed)


def urllib_request(url):
    import urllib.request
    return urllib.request.Request(url)


class HeaderTest(unittest.TestCase):
    def test_identity_and_qr_headers(self):
        self.assertEqual(ilink.CLIENT_VERSION, "65536")
        self.assertEqual(config.BOT_AGENT, "GrokWechatBridge/1.0.0")
        self.assertNotIn("OpenClaw", config.BOT_AGENT)
        post = ilink.qr_post_headers()
        get = ilink.qr_get_headers()
        self.assertEqual(post["AuthorizationType"], "ilink_bot_token")
        self.assertIn("X-WECHAT-UIN", post)
        self.assertNotIn("Authorization", post)
        self.assertEqual(post["iLink-App-Id"], "bot")
        self.assertEqual(post["iLink-App-ClientVersion"], "65536")
        for forbidden in ("Authorization", "AuthorizationType", "X-WECHAT-UIN", "Content-Type"):
            self.assertNotIn(forbidden, get)
        info = ilink.base_info()
        self.assertEqual(info["channel_version"], "1.0.0")
        self.assertRegex(info["bot_agent"], r"^[A-Za-z0-9_.-]{1,32}/[A-Za-z0-9_.+\-]{1,32}$")


class CredentialTest(unittest.TestCase):
    def test_private_mode_and_rejected_baseurl(self):
        ilink.save_creds({
            "baseurl": "https://ilinkai.weixin.qq.com",
            "bot_token": "token-value",
            "ilink_bot_id": BOT,
            "ilink_user_id": OWNER,
        })
        self.assertEqual(stat.S_IMODE(os.stat(ilink.CRED).st_mode), 0o600)
        os.chmod(ilink.CRED, 0o644)
        with self.assertRaises(ilink.IlinkError):
            ilink.load_creds()
        os.chmod(ilink.CRED, 0o600)
        with open(ilink.CRED, "w", encoding="utf-8") as fh:
            json.dump({
                "baseurl": "https://evil.example",
                "bot_token": "token-value",
                "ilink_bot_id": BOT,
                "ilink_user_id": OWNER,
            }, fh)
        os.chmod(ilink.CRED, 0o600)
        called = []
        original = ilink.request
        ilink.request = lambda *args, **kwargs: called.append(args)
        try:
            with self.assertRaises(ilink.IlinkError):
                ilink.post("ilink/bot/getupdates", {})
        finally:
            ilink.request = original
        self.assertEqual(called, [])

    def test_world_readable_webhook_file_is_not_read(self):
        path = os.path.join(TMP, "webhook.env")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("WECHAT_WEBHOOK_KEY=supersecretvalue\n")
        os.chmod(path, 0o644)
        self.assertEqual(config.webhook_key(), "")
        self.assertTrue(any("0600" in item for item in config.CONFIG_ERRORS))
        self.assertNotIn("supersecretvalue", " ".join(config.CONFIG_ERRORS))
        os.chmod(path, 0o600)


class LoginMockTest(unittest.TestCase):
    def setUp(self):
        for name in (ilink.CRED, ilink.QR_SESSION, bind.QR_PNG, bind.QR_URL):
            if os.path.exists(name):
                os.remove(name)

    def test_qr_only_posts_official_endpoint_and_does_not_listen(self):
        calls = []

        def http(url, **kwargs):
            calls.append((url, kwargs))
            self.assertEqual(kwargs["method"], "POST")
            self.assertNotIn("Authorization", kwargs["headers"])
            self.assertIn("AuthorizationType", kwargs["headers"])
            self.assertIn("X-WECHAT-UIN", kwargs["headers"])
            self.assertEqual(json.loads(kwargs["body"]), {"local_token_list": []})
            self.assertNotIn(b"base_info", kwargs["body"])
            return {"qrcode": "qr-value", "qrcode_img_content": "https://ilinkai.weixin.qq.com/qr/example"}

        self.assertEqual(bind.qr_only(http=http), 0)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].startswith("https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3"))
        self.assertFalse(os.path.exists(ilink.CRED))
        self.assertFalse(os.path.exists(os.path.join(TMP, "forward.pid")))
        self.assertEqual(stat.S_IMODE(os.stat(bind.QR_PNG).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(ilink.QR_SESSION).st_mode), 0o600)

    def test_wait_saves_credentials_without_printing_token(self):
        config.atomic_json(ilink.QR_SESSION, {
            "qrcode": "qr-value",
            "qrcode_img_content": "https://ilinkai.weixin.qq.com/qr/example",
            "baseurl": "https://ilinkai.weixin.qq.com",
            "started_at": 1000,
        })
        calls = []

        def http(url, **kwargs):
            calls.append(url)
            self.assertEqual(kwargs["method"], "GET")
            self.assertNotIn("Authorization", kwargs["headers"])
            self.assertNotIn("AuthorizationType", kwargs["headers"])
            return {
                "status": "confirmed",
                "bot_token": "token-value",
                "ilink_bot_id": BOT,
                "ilink_user_id": OWNER,
                "baseurl": "https://sz.weixin.qq.com",
            }

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = bind.wait_for_scan(http=http, clock=lambda: 1001, sleeper=lambda _s: None)
        self.assertEqual(code, 0)
        self.assertIn("get_qrcode_status", calls[0])
        self.assertNotIn("getupdates", calls[0])
        saved = json.load(open(ilink.CRED, encoding="utf-8"))
        self.assertEqual(saved["baseurl"], "https://sz.weixin.qq.com")
        self.assertEqual(saved["ilink_user_id"], OWNER)
        self.assertNotIn("token-value", buf.getvalue())
        self.assertFalse(os.path.exists(ilink.QR_SESSION))

    def test_binded_redirect_does_not_save_a_token(self):
        config.atomic_json(ilink.QR_SESSION, {
            "qrcode": "qr-value", "baseurl": "https://ilinkai.weixin.qq.com", "started_at": 1000,
            "qrcode_img_content": "x",
        })

        def http(url, **kwargs):
            return {"status": "binded_redirect", "bot_token": "should-not-save"}

        code = bind.wait_for_scan(http=http, clock=lambda: 1001, sleeper=lambda _s: None)
        self.assertEqual(code, 3)
        self.assertFalse(os.path.exists(ilink.CRED))

    def test_evil_redirect_stops(self):
        config.atomic_json(ilink.QR_SESSION, {
            "qrcode": "qr-value", "baseurl": "https://ilinkai.weixin.qq.com", "started_at": 1000,
            "qrcode_img_content": "x",
        })
        calls = []

        def http(url, **kwargs):
            calls.append(url)
            return {"status": "scaned_but_redirect", "redirect_host": "evil.example"}

        with self.assertRaises(ilink.IlinkError):
            bind.wait_for_scan(http=http, clock=lambda: 1001, sleeper=lambda _s: None)
        self.assertTrue(all("evil.example" not in url for url in calls))
        self.assertFalse(os.path.exists(ilink.CRED))

    def test_old_qr_is_not_polled(self):
        config.atomic_json(ilink.QR_SESSION, {
            "qrcode": "qr-value", "baseurl": "https://ilinkai.weixin.qq.com", "started_at": 0,
            "qrcode_img_content": "x",
        })
        called = []
        code = bind.wait_for_scan(http=lambda *a, **k: called.append(1), clock=lambda: 10000, sleeper=lambda _s: None)
        self.assertEqual(code, 4)
        self.assertEqual(called, [])


class ForwardMockTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop("WECHAT_FORWARD_ENABLED", None)
        os.environ.pop("WECHAT_WEBHOOK_URL", None)
        os.environ.pop("WECHAT_WEBHOOK_KEY", None)
        self.original_request = ilink.request
        self.original_post = ilink.post

    def tearDown(self):
        ilink.request = self.original_request
        ilink.post = self.original_post
        os.environ.pop("WECHAT_FORWARD_ENABLED", None)

    def test_require_forward_does_not_touch_network_when_disabled(self):
        def boom(*_a, **_k):
            raise AssertionError("network was contacted")
        ilink.request = boom
        ilink.urlopen = boom
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = forward.run(["--require-forward"])
        self.assertEqual(code, 2)
        self.assertIn("forward_enabled=no", buf.getvalue())
        self.assertIn("network=not-contacted", buf.getvalue())

    def test_check_does_not_print_the_key(self):
        os.environ["WECHAT_WEBHOOK_URL"] = WEBHOOK
        os.environ["WECHAT_WEBHOOK_KEY"] = "unit-test-webhook-key-9f3a"
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(forward.run(["--check"]), 0)
        self.assertNotIn("unit-test-webhook-key-9f3a", buf.getvalue())
        self.assertIn("webhook=ok", buf.getvalue())
        self.assertIn("webhook_key=present", buf.getvalue())
        self.assertIn("qr_ttl_seconds=300", buf.getvalue())

    def test_ready_preflight_still_does_not_connect(self):
        os.environ["WECHAT_FORWARD_ENABLED"] = "1"
        os.environ["WECHAT_WEBHOOK_URL"] = WEBHOOK
        os.environ["WECHAT_WEBHOOK_KEY"] = "unit-test-webhook-key-9f3a"
        ilink.save_creds({
            "baseurl": "https://ilinkai.weixin.qq.com", "bot_token": "token-value",
            "ilink_bot_id": BOT, "ilink_user_id": OWNER,
        })

        def boom(*_a, **_k):
            raise AssertionError("network was contacted")
        ilink.request = boom
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = forward.run(["--require-forward"])
        self.assertEqual(code, 0)
        self.assertIn("READY", buf.getvalue())
        self.assertNotIn("unit-test-webhook-key-9f3a", buf.getvalue())

    def test_owner_kept_stranger_and_group_dropped(self):
        ilink.save_creds({
            "baseurl": "https://ilinkai.weixin.qq.com", "bot_token": "token-value",
            "ilink_bot_id": BOT, "ilink_user_id": OWNER,
        })

        def fake_post(endpoint, body, timeout=15):
            self.assertEqual(endpoint, "ilink/bot/getupdates")
            self.assertNotIn("stranger-secret", json.dumps(body))
            return json.dumps({
                "ret": 0,
                "get_updates_buf": "cursor-1",
                "msgs": [
                    {"message_type": 1, "from_user_id": "stranger@im.wechat", "to_user_id": BOT,
                     "message_id": 1, "context_token": "stranger-token",
                     "item_list": [{"type": 1, "text_item": {"text": "stranger-secret"}}]},
                    {"message_type": 1, "from_user_id": OWNER, "to_user_id": BOT, "group_id": "g1",
                     "message_id": 2, "item_list": [{"type": 1, "text_item": {"text": "group-secret"}}]},
                    {"message_type": 1, "from_user_id": OWNER, "to_user_id": BOT, "message_id": 3,
                     "create_time_ms": 50, "context_token": "owner-token",
                     "item_list": [{"type": 1, "text_item": {"text": "owner-secret"}}]},
                ],
            })
        ilink.post = fake_post
        status, messages = forward.fetch()
        self.assertEqual(status, "ok")
        self.assertEqual([item["message_id"] for item in messages], [3])
        raw_state = open(ilink.STATE, encoding="utf-8").read()
        self.assertIn("cursor-1", raw_state)
        self.assertIn("owner-token", raw_state)
        self.assertNotIn("stranger-secret", raw_state)
        self.assertNotIn("group-secret", raw_state)
        self.assertNotIn("owner-secret", raw_state)
        self.assertNotIn("stranger-token", raw_state)
        posted = []

        class Clock:
            def __init__(self):
                self.t = 1000.0
            def __call__(self):
                return self.t

        clock = Clock()
        batcher = forward.Batcher(
            os.path.join(TMP, "pending-owner.json"), quiet=3, cap=60,
            poster=lambda body: posted.append(body) or (200, "NOT-A-REPLY"),
            clock=clock, history_path=os.path.join(TMP, "hist-owner.log"),
        )
        forward.handle(messages, batcher, peers=(OWNER, BOT))
        clock.t += 3
        self.assertTrue(batcher.maybe_flush())
        body = posted[0]
        encoded = json.dumps(body, ensure_ascii=False)
        self.assertIn("owner-secret", encoded)
        self.assertNotIn("stranger-secret", encoded)
        self.assertNotIn("group-secret", encoded)
        self.assertNotIn("owner-token", encoded)
        self.assertNotIn("from_user_id", encoded)
        self.assertNotIn("NOT-A-REPLY", encoded)
        self.assertIn("accepted this run only", body["delivery"]["webhook_http_200"])
        self.assertEqual(body["delivery"]["reply_args"], ["--reply-to-ms", "50"])

    def test_webhook_200_discards_body(self):
        os.environ["WECHAT_WEBHOOK_URL"] = WEBHOOK
        os.environ["WECHAT_WEBHOOK_KEY"] = "unit-test-webhook-key-9f3a"

        def fake_request(url, **kwargs):
            self.assertEqual(url, WEBHOOK)
            self.assertEqual(kwargs["redirects"], "none")
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer unit-test-webhook-key-9f3a")
            return 200, b'{"reply":"do-not-use","runUuid":"abc"}'
        ilink.request = fake_request
        self.assertEqual(forward.post_webhook({"source": "wechat-owner"}), (200, ""))

    def test_minus_14_pauses_without_forwarding_text(self):
        def fake_post(endpoint, body, timeout=15):
            return json.dumps({"ret": -14, "msgs": [{"text": "paused-secret"}]})
        ilink.post = fake_post
        status, messages = forward.fetch()
        self.assertEqual(status, "pause")
        self.assertEqual(messages, [])

    def test_selftest_removed(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = forward.run(["--selftest"])
        self.assertEqual(code, 2)
        self.assertIn("removed", buf.getvalue())


class BatcherTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "pending-test.json")
        self.hist = os.path.join(TMP, "hist-test.log")
        for path in (self.path, self.hist):
            if os.path.exists(path):
                os.remove(path)
        self.sent, self.clock = [], _Clock()

    def poster(self, body):
        self.sent.append(body)
        return (200, "ok")

    def mk(self):
        return forward.Batcher(self.path, quiet=3, cap=60, poster=self.poster, clock=self.clock, history_path=self.hist)

    def msg(self, text, ms):
        return {"items": [{"type": 1, "text": text}], "texts": [text], "create_time_ms": ms, "message_id": ms}

    def test_quiet_flush_batches_burst(self):
        batcher = self.mk()
        batcher.add(self.msg("a", 1))
        self.clock.t += 1
        batcher.add(self.msg("b", 2))
        self.assertFalse(batcher.maybe_flush())
        self.clock.t += 3
        self.assertTrue(batcher.maybe_flush())
        self.assertEqual(self.sent[0]["count"], 2)
        self.assertEqual(self.sent[0]["trigger_ms"], 2)
        self.assertIn("--reply-to-ms 2", self.sent[0]["reply_rule"])
        self.assertIn("Tester：a b", open(self.hist, encoding="utf-8").read())
        self.assertNotIn("renew", json.dumps(self.sent[0]).lower())

    def test_failed_flush_is_kept(self):
        batcher = forward.Batcher(self.path, quiet=3, cap=60, poster=lambda body: None, clock=self.clock, history_path=self.hist)
        batcher.add(self.msg("x", 5))
        self.clock.t += 5
        self.assertFalse(batcher.maybe_flush())
        self.assertEqual(len(json.load(open(self.path, encoding="utf-8"))["messages"]), 1)
        restored = self.mk()
        self.assertEqual(len(restored.msgs), 1)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)


class _Clock:
    def __init__(self):
        self.t = 1000.0
    def __call__(self):
        return self.t


class SendTest(unittest.TestCase):
    def setUp(self):
        os.environ.pop("WECHAT_SEND_ENABLED", None)
        self.original = ilink.send_text
        self.calls = []

        def fake(text, context_token=None):
            self.calls.append((text, context_token))
            return True, 0
        ilink.send_text = fake
        ilink.save_creds({
            "baseurl": "https://ilinkai.weixin.qq.com", "bot_token": "token-value",
            "ilink_bot_id": BOT, "ilink_user_id": OWNER,
        })

    def tearDown(self):
        ilink.send_text = self.original
        os.environ.pop("WECHAT_SEND_ENABLED", None)

    def test_disabled_by_default(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = send.run(["hello", "--reply-to-ms", "10"])
        self.assertEqual(code, 2)
        self.assertEqual(self.calls, [])
        self.assertIn("disabled", buf.getvalue())

    def test_recipient_override_and_proactive_are_refused(self):
        os.environ["WECHAT_SEND_ENABLED"] = "1"
        self.assertEqual(send.run(["hello", "--to", "stranger@im.wechat"]), 2)
        self.assertEqual(send.run(["--app", "reminder"]), 2)
        self.assertEqual(self.calls, [])

    def test_enabled_send_goes_to_saved_owner_and_supersedes(self):
        os.environ["WECHAT_SEND_ENABLED"] = "1"
        ilink.save_state({"last_inbound_ms": 2000, "context_tokens": {OWNER: "ctx"}})
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(send.run(["answer", "--reply-to-ms", "1000"]), 4)
        self.assertEqual(self.calls, [])
        self.assertIn("SUPERSEDED", buf.getvalue())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(send.run(["answer", "--reply-to-ms", "2000"]), 0)
        self.assertEqual(self.calls[0][0], "answer")
        self.assertNotIn("token-value", buf.getvalue())


class MediaTest(unittest.TestCase):
    def test_decrypt_roundtrip_and_keys(self):
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        import base64
        key = bytes(range(16))
        data = b"\x89PNG fake image"
        pad = 16 - len(data) % 16
        enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
        blob = enc.update(data + bytes([pad]) * pad) + enc.finalize()
        self.assertEqual(media.decrypt(blob, key), data)
        self.assertEqual(media.sniff_ext(data), "png")
        self.assertEqual(media.parse_key({"aeskey": key.hex()}), key)
        self.assertEqual(media.parse_key({"media": {"aes_key": base64.b64encode(key).decode()}}), key)
        self.assertEqual(media.parse_key({"media": {"aes_key": base64.b64encode(key.hex().encode()).decode()}}), key)

    def test_summarize_drops_keys(self):
        summary = media.summarize({"type": 3, "voice_item": {"text": "你好", "media": {"aes_key": "x"}, "aeskey": "abcd"}})
        encoded = json.dumps(summary, ensure_ascii=False)
        self.assertEqual(summary["text"], "你好")
        self.assertNotIn("aes", encoded)
        self.assertNotIn("media", encoded)

    def test_cdn_download_has_no_authorization_header(self):
        captured = []

        class Response:
            status = 200
            def read(self):
                return b"abc"
            def getcode(self):
                return 200
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False

        def fake_open(req, timeout, opener):
            captured.append(req)
            return Response()

        original = ilink.urlopen
        ilink.urlopen = fake_open
        try:
            self.assertEqual(media.download("https://novac2c.cdn.weixin.qq.com/c2c/download?encrypted_query_param=abc"), b"abc")
        finally:
            ilink.urlopen = original
        joined = " ".join(captured[0].header_items() and [k for k, _v in captured[0].header_items()])
        self.assertNotIn("authorization", joined.lower())

    def test_business_refusal_is_not_success(self):
        ok, _parsed = ilink.business_ok('{"ret": 0}')
        self.assertTrue(ok)
        ok, parsed = ilink.business_ok('{"ret": -2, "errcode": -2}')
        self.assertFalse(ok)
        self.assertEqual(parsed["ret"], -2)
        self.assertFalse(ilink.business_ok("not-json")[0])


class TreeTest(unittest.TestCase):
    def test_program_files_do_not_impersonate_or_nudge(self):
        banned = ("maybe_nudge", "nudge_text", "wechat_secrets_file", "chihao", "openclaw-weixin-", '"openclaw"')
        for name in os.listdir(ROOT):
            if not name.endswith((".py", ".sh")):
                continue
            with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
                text = fh.read().lower()
            for word in banned:
                self.assertNotIn(word, text, "%s contains %s" % (name, word))
        watchdog = open(os.path.join(ROOT, "watchdog.sh"), encoding="utf-8").read()
        self.assertNotIn("nohup", watchdog)
        self.assertNotIn("send.py", watchdog)
        self.assertNotIn("run_forward", watchdog)
        install = open(os.path.join(ROOT, "install.sh"), encoding="utf-8").read()
        self.assertIn("--no-index", install)
        self.assertNotIn("pypi.org", install)

    def test_poll_and_watchdog_do_not_connect(self):
        poll = subprocess.run([sys.executable, os.path.join(ROOT, "poll.py")], capture_output=True, text=True)
        self.assertEqual(poll.returncode, 2)
        self.assertIn("disabled", poll.stdout)
        watch = subprocess.run(["bash", os.path.join(ROOT, "watchdog.sh")], capture_output=True, text=True)
        self.assertEqual(watch.returncode, 0)
        self.assertIn("disabled", watch.stdout)

    def test_install_without_wheels_does_not_create_a_venv(self):
        wheels = os.path.join(ROOT, "wheels")
        has_wheels = os.path.isdir(wheels) and any(name.endswith(".whl") for name in os.listdir(wheels))
        if has_wheels:
            with open(os.path.join(ROOT, "install.sh"), encoding="utf-8") as fh:
                install = fh.read()
            self.assertIn("--no-index", install)
            self.assertNotIn("pypi.org", install)
            return
        result = subprocess.run(["bash", os.path.join(ROOT, "install.sh")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not contact PyPI", result.stdout)
        self.assertFalse(os.path.isdir(os.path.join(ROOT, "venv")))

    def test_verify_wheels_accepts_matching_hash(self):
        directory = tempfile.mkdtemp(prefix="wheel-test-")
        wheels = os.path.join(directory, "wheels")
        os.makedirs(wheels)
        blob = b"wheel-bytes"
        name = "example.whl"
        with open(os.path.join(wheels, name), "wb") as fh:
            fh.write(blob)
        digest = hashlib.sha256(blob).hexdigest()
        with open(os.path.join(directory, "SHA256SUMS"), "w", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (digest, name))
        script = open(os.path.join(ROOT, "verify_wheels.py"), encoding="utf-8").read()
        # Run a copy whose ROOT is the temp directory by executing the function
        # against files we just wrote through a subprocess with the script relocated.
        relocated = os.path.join(directory, "verify_wheels.py")
        with open(relocated, "w", encoding="utf-8") as fh:
            fh.write(script)
        result = subprocess.run([sys.executable, relocated], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("wheel hashes ok", result.stdout)


class HistoryClockTest(unittest.TestCase):
    def test_history_stays_private(self):
        path = os.path.join(TMP, "history-mode.log")
        history.append(history.user_line([{"items": [{"type": 1, "text": "hi"}], "create_time_ms": 0}]), path)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertIn("Tester：hi", open(path, encoding="utf-8").read())
        # The zone name is accepted; this only checks the helper does not throw.
        self.assertTrue(datetime.now(ZoneInfo("Asia/Shanghai")))


if __name__ == "__main__":
    unittest.main()
