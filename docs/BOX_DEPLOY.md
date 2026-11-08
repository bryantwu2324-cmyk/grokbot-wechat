# 在 box 上安装和验收

父级不需要 clone 仓库。只使用交付的压缩包。压缩包里的 `install.sh` 不会访问 PyPI，不会启动监听，也不会发送消息。

## 下一步先做哪一件

**先做 webhook，再做扫码登录。**

二维码有时间限制。官方客户端把一次登录会话记为 5 分钟（`ACTIVE_LOGIN_TTL_MS = 300000`）。协议没有另外公布服务端有效期，服务端可以更早返回 `expired`。扫码时人必须在手机前。Webhook 只是在官方面板创建 routine，再把 URL 和 key 写进本机文件，这期间不连接微信。

两条都准备好以后，转发和发送仍然是关的。父级先看登录命令的结果，再决定要不要把开关改成 `1`。

## 凭据目录

默认是 `~/.grokbot-wechat`。可以用环境变量 `BRIDGE_DATA_DIR` 改到别的地方，但必须在安装目录外面。

- 目录权限 `0700`
- `webhook.env`、`credentials.json`、`qr_session.json`、`qr.png`、`qr_url.txt`、`state.json`、`pending.json`、`history.log` 都是 `0600`
- 这些文件不能进 git、PR 或聊天

本桥只读这个目录里的 `webhook.env`，或者进程里已经存在的同名环境变量。它不读 Cursor / Grok 的设置文件、cookie 或数据库。

## 0. 安装

要求：Linux x86_64 或 aarch64，CPython 3.11 及以上，并且自带 `venv` 模块（Debian/Ubuntu 的软件包名一般是 `python3-venv`）。Pillow 的 wheel 需要 glibc 2.27 或更新。不要用代理来跑这个程序；程序会忽略 `HTTP(S)_PROXY`。

```bash
tar -xzf grokbot-wechat-box-1.0.0.tar.gz
cd grokbot-wechat
bash install.sh
```

安装结束时转发是关的，发送是关的，没有进程在跑。

## 1. 父级创建 boss 的 Webhook routine

在**现有 boss** 的聊天里说要加一个 webhook routine，指令用 `routines/inbound-webhook.md`。不要建定时 routine，不要打开 Test（Test 会做真实工作，会消耗用量）。

然后在桌面端打开这个 routine 的 Webhook 栏，复制：

- POST to
- key

URL 必须是 `https://api2.cursor.sh/automations/webhook/<id>`，没有 query。如果面板给出的主机不是这个，停下来报告，不要改允许列表。

key 不要贴进聊天。使用的人从官方面板复制后，在 box 上写入凭据文件。secret-request 的作用是避免把 key 打进对话记录；本程序不会因此去打开 app 内部文件。若 secret-request 的值只有内部凭据库能看见，就不要去读那个库，改由使用的人把从面板复制的值写入下面这个文件。

```bash
umask 077
edit ~/.grokbot-wechat/webhook.env
chmod 600 ~/.grokbot-wechat/webhook.env
```

文件内容保持这样，开关先不要改：

```
WECHAT_WEBHOOK_URL=https://api2.cursor.sh/automations/webhook/<面板上的 id>
WECHAT_WEBHOOK_KEY=<面板上的 key>
WECHAT_FORWARD_ENABLED=0
WECHAT_SEND_ENABLED=0
```

检查不会联网，也不会打印 key：

```bash
./status.sh
```

期望看到 `forward_enabled=no`、`send_enabled=no`、`webhook=ok`、`webhook_key=present`、`network=not-contacted`。

## 2. 只登录

人在手机前时再做。这一步不会启动收消息，也不会发送。

```bash
./login-qr.sh
```

它会写出：

- `~/.grokbot-wechat/qr.png`
- `~/.grokbot-wechat/qr_url.txt`

用绑定者本人的微信扫 `qr.png`。不要把链接贴进聊天或日志。客户端会话上限是 **300 秒**。超过这个时间，或服务端返回 `expired`，重新运行 `./login-qr.sh`。这个包不会在背后自动刷新二维码，避免人正在看的图被换掉。

扫完以后父级再单独运行：

```bash
./login-wait.sh
```

手机若显示数字，把数字写入 `~/.grokbot-wechat/verify_code.txt` 并 `chmod 600`。

成功时命令打印凭据路径，并打印打码后的用户 id。它不打印 token。`credentials.json` 应为 `0600`。此时 `status.sh` 里 `credentials=ok`，`process=stopped`。

如果结果是 `binded_redirect`，服务端没有签发新凭据。命令不会把账号标成已连接。需要在微信里解除原来的绑定后再登录。不要把它当成成功。

## 3. 父级确认之后才监听和允许回复

确认两件事：webhook 是 boss 面板上的那个 routine，登录的是本人。然后才编辑 `webhook.env`：

```
WECHAT_FORWARD_ENABLED=1
WECHAT_SEND_ENABLED=1
```

```bash
./start.sh
./status.sh
./stop.sh
```

`start.sh` 在开关不是 `1`、URL 不合法或凭据不可读时会退出，不会留下进程。`stop.sh` 只向命令行里带 `forward.py` 的那个 pid 发 SIGTERM。

boss 回复微信时运行 payload 里的 `delivery.reply_command`，也就是安装目录中的 `reply.sh`：

```bash
./reply.sh "回复正文" --reply-to-ms <trigger_ms>
```

退出码：`0` 微信接受了文本；`2` 本机拒绝（开关关闭、参数不对）；`3` 微信拒绝或网络失败，没有排队；`4` 绑定者有更新的消息，什么都没发。

## 4. 离线验收

在安装目录：

```bash
./venv/bin/python -m unittest discover -s tests -v
```

全部通过只说明 mock 下的协议和权限符合预期。它不是扫码成功，也不是发消息成功。

另外可以看：

- `./login-qr.sh` 之前，`status.sh` 是 `process=stopped`
- 只跑 `./login-qr.sh` 时，不会出现 `forward.pid`
- `bash watchdog.sh` 打印 disabled，并且不会把监听拉起来
- `python3 poll.py` 退出码 2

真实收发要等使用的人在 box 上打开开关之后，由父级另行验证。这次交付没有做那一步。

## 不要做的事

- 不要安装 OpenClaw，不要把 `bot_agent` 改回 OpenClaw
- 不要建每 15 分钟的 watchdog routine，不要让 boss 定时发微信
- 不要运行旧的 `forward.py --selftest`（现在会直接退出）
- 不要把凭据、二维码链接、webhook key 放进仓库、PR、issue 或聊天
- 不要为了绕过域名检查去改允许列表，除非面板或腾讯文档先证明那是官方主机
