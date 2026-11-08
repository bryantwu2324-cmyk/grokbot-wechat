# grokbot-wechat

把**绑定者本人**的微信文字交给已经存在的 Grok Bot boss，再由 boss 调用本机 `reply.sh` 把回复送回微信。

这不是另一个模型，也不安装上游渠道包。微信侧用腾讯公开的 iLink HTTP API，Grok 侧用官方 Webhook routine。HTTP 200 只表示 routine 已开始，不表示回复已经产生。

转发和发送默认关闭。没有续期提醒，没有定时主动发送。陌生人消息和群消息默认丢弃。

## 文档

- 审查结论：[docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md)
- box 安装、登录、启停和验收：[docs/BOX_DEPLOY.md](docs/BOX_DEPLOY.md)
- 依赖和 wheel 摘要：[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)
- boss routine 指令：[routines/inbound-webhook.md](routines/inbound-webhook.md)

box 上的父级使用交付的压缩包，不 clone 本仓库。`install.sh` 只在压缩包自带 `wheels/` 时离线安装。

## 命令

| 命令 | 作用 |
|---|---|
| `./login-qr.sh` | 只生成一张二维码，不监听、不发送 |
| `./login-wait.sh` | 等待刚才那张二维码被确认 |
| `./status.sh` | 查看开关和凭据是否就绪，不联网 |
| `./start.sh` | 仅当 `WECHAT_FORWARD_ENABLED=1` 时开始监听 |
| `./stop.sh` | 停止本目录启动的监听进程 |
| `./reply.sh "文本" --reply-to-ms <trigger_ms>` | boss 用来回微信的本机命令 |

凭据目录默认是 `~/.grokbot-wechat`（`0700`）。二维码客户端会话上限是 5 分钟；服务端可能更早返回 `expired`。建议先写好 webhook，再扫码。

## 离线测试

```bash
python3 -m unittest discover -s tests -v
```

测试使用假的 HTTP 响应。通过不等于已经登录或已经发出微信。

## 许可

MIT，见 [LICENSE](LICENSE)。
