# 安全审查结论

审查对象是公开仓库当前这棵树（初始提交 `9dfedc9`）以及这次在新分支上的修复。这里不保证仓库以外的历史、聊天记录或旧机器上的副本已经同步检查过。

这次没有扫码登录，没有发送微信，没有调用模型，没有拿真实 token。下面凡是写“通过”的，都是本机 mock 或静态检查，不是线上成功。

## 目标是否落在公开接口里

目标是：绑定者本人的微信消息交给**已经存在的** Grok Bot boss，boss 再通过本机命令把回复送回微信。

公开依据：

- 微信侧使用腾讯公开的 iLink HTTP JSON 协议：`https://ilinkai.weixin.qq.com` 上的 `get_bot_qrcode`、`get_qrcode_status`、`getupdates`、`sendmessage`、`notifystart`、`notifystop`，媒体走 `*.weixin.qq.com`。协议说明见 `https://github.com/Tencent/openclaw-weixin/blob/main/docs/protocol_zh_CN.md`。这里只用这份协议，不安装、不运行 OpenClaw。
- Grok Bot 侧使用官方 Webhook routine。官方说明：向面板给出的 URL POST，带 `Authorization: Bearer <key>`；**HTTP 200 只表示 run 已开始，不表示指令已经做完**。见 `https://cursor.com/help/grok-bot/routines`。Cursor 自己的插件说明里，这个 URL 的形状是 `https://api2.cursor.sh/automations/webhook/<id>`。

这个目标不需要 Grok Bot 内部 API、cookie、私有数据库，也不需要再接一个独立模型。回复接口是本机的 `reply.sh` / `send.py`。boss 在 webhook run 里调用它。

## 修复前的问题

- 任何 `message_type == 1` 的消息都会转发，包括陌生人；`send.py --to` 可以指定别人；最近一个说话的人会变成默认收件人。
- 转发进程默认就会轮询并 POST。发送命令默认就会发。
- `outbox.py` 会在大约 18 小时后自动发续期提醒，也有定时补发。这不是协议里的接口，是作者自己的观察，而且和“不要主动发、不要定时发”直接冲突。
- `bot_agent` 写成 `OpenClaw`，`client_id` 也带 `openclaw-weixin-`。这不是本桥的身份。
- 二维码 POST 缺少协议要求的 `AuthorizationType` 和 `X-WECHAT-UIN`。GET 和 POST 共用同一组头。
- `baseurl`、QR `redirect_host`、媒体 `full_url` 会跟着服务端字符串走，没有限制在 `weixin.qq.com`。Webhook URL 也没有限制，响应体还会被记进日志，并可能被当成成功内容。
- 会读取代码目录旁的 `.env`，还会在任意 JSON 里递归寻找 `WECHAT_WEBHOOK_KEY`。这和“不要读内部 app 设置”冲突。
- `forward.py --selftest` 会向真实 webhook POST，从而启动一次真实的 boss run。
- `watchdog.sh` 被设计成每 15 分钟由 Grok 定时 routine 拉起，并在重启多次后主动发微信。

## 现在的行为

- 只接受扫码得到的 `ilink_user_id` 发来的单聊用户消息。群、其他人、bot 回声都丢弃，不下载他们的媒体，不把正文写入 state。
- `WECHAT_FORWARD_ENABLED` 和 `WECHAT_SEND_ENABLED` 只有精确等于 `1` 才打开。缺省是关。
- 没有 nudge，没有定时主动发送，没有失败后的自动补发。`watchdog.sh` 现在什么都不做，避免旧 cron 把监听又拉起来。
- 发送没有 `--to` 可以改收件人。收件人永远是凭据里的绑定者。
- Webhook 只接受 `https://api2.cursor.sh/automations/webhook/<id>`，不跟随重定向，不记录响应体。只有 HTTP 200 算“run 已接受”。200 的 body 不会变成微信回复。
- 微信 API 和 CDN 只走 `https://*.weixin.qq.com`，二维码第一步固定是 `https://ilinkai.weixin.qq.com`。HTTP 重定向如果离开这个域名就停止。环境变量里的 HTTP(S)_PROXY 被忽略，避免 token 和 webhook key 被送到代理。
- 凭据目录默认 `~/.grokbot-wechat`，必须在安装目录外面，目录 `0700`，凭据和 webhook.env 不是 `0600` 就拒绝读取。
- 身份是 `GrokWechatBridge/1.0.0`，`channel_version` 是 `1.0.0`，`iLink-App-Id` 仍是协议写明的 `bot`。没有把产品名报成 OpenClaw。
- 登录分成 `login-qr.sh` 和 `login-wait.sh`。两个命令都不启动收消息，也不发送。

## 运行时会联系谁

只应出现这些直连：

| 用途 | 主机 |
|---|---|
| 二维码和 bot API | `ilinkai.weixin.qq.com`，以及确认响应或 `scaned_but_redirect` 给出的 `*.weixin.qq.com` |
| 媒体 | `novac2c.cdn.weixin.qq.com` 或消息里给出的其他 `*.weixin.qq.com` |
| 唤醒 boss | `api2.cursor.sh` |

没有把消息交给第三方托管来转发。安装包里的 wheel 是随包带来的，`install.sh` 使用 `pip --no-index`，安装时也不访问 PyPI。

如果下面任一情况出现，就停，不要改代码去绕：

- 面板上的 webhook 主机不是 `api2.cursor.sh`
- 二维码重定向主机不是 `*.weixin.qq.com`
- 服务端拒绝 `GrokWechatBridge/1.0.0` 或 `channel_version=1.0.0`
- 机器必须通过 HTTP 代理或第三方网关才能到达上述主机

这些都还没有用真实账号验证。协议没有说服务端一定会接受一个非 OpenClaw 的 `bot_agent`。公开文档写明 `bot_agent` 不参与鉴权，只用于日志归因，所以这里按文档使用自己的名字。若线上拒绝，这是阻塞，不是再去冒充 OpenClaw 的理由。

## 仍然存在的限制

- 出站只有文本。图片、文件、视频的发送没有实现。入站媒体会解密到凭据目录，路径交给 boss，密钥不放进 webhook。
- 微信是否存在“用户太久不说话就不能主动发”的窗口，协议说明里没有写。因此这里不再做续期提醒。boss 调用 `reply.sh` 时如果微信拒绝，命令以退出码 3 结束，不排队、不自动重发。
- Webhook 超时无法区分“run 没开始”和“run 已经开始但响应丢了”。这一次不立即重试，消息留在本机 `pending.json`，60 秒后的下一轮才会再 POST 一次。这仍可能在极端情况下让 boss 跑两次。没有更安全的公开幂等接口可用。
- boss 本身是模型。微信正文可能试图改写它的指令。本机命令不接受别的收件人，发送开关关闭时它也不能发。这不能阻止模型在 Grok 聊天里说错话。
- `ret` 缺失时，按协议对 `sendmessage` 不视为失败。完全无法解析的响应视为失败。
- 审查没有覆盖初始提交之前不在这个 git 树里的文件。

## 测试

`python3 -m unittest discover -s tests -v` 使用假的 HTTP 响应检查协议字段、域名、权限和默认关闭。它不会生成真实二维码，也不会得到真实的登录成功。
