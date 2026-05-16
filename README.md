# ddns-cf

一个足够精简的 Linux 服务器 DDNS 服务，只支持 Cloudflare，支持 IPv4 `A` 和 IPv6 `AAAA` 记录，更新成功或失败时可选 Telegram 通知。

## 安装

```bash
uv sync
```

## 配置

复制示例配置：

```bash
sudo mkdir -p /etc/ddns-cf
sudo cp examples/config.toml /etc/ddns-cf/config.toml
sudo chmod 600 /etc/ddns-cf/config.toml
```

最小配置示例：

```toml
[cloudflare]
api_token = "cf_api_token"
zone_id = "cf_zone_id"

[runtime]
interval_seconds = 300
timeout_seconds = 10
notify_on_no_change = false

[[records]]
name = "example.com"
type = "A"

[[records]]
name = "example.com"
type = "AAAA"

[telegram]
enabled = true
bot_token = "tg_bot_token"
chat_id = "123456789"
```

## 运行

单次检查：

```bash
uv run ddns-cf --config /etc/ddns-cf/config.toml --once
```

常驻运行：

```bash
uv run ddns-cf --config /etc/ddns-cf/config.toml
```

systemd 示例在 `systemd/ddns-cf.service`。部署时需要按实际安装路径调整 `WorkingDirectory` 和 `ExecStart`。

## 检查

```bash
uv run ruff format .
uv run ruff check .
uv run ty check .
uv run pytest
```
