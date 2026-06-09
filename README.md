# ddns-cf

一个足够精简的 Linux 服务器 DDNS 服务，只支持 Cloudflare，支持 IPv4 `A` 和 IPv6 `AAAA` 记录，更新成功或失败时可选 Telegram 通知。

## 快速部署

一键交互式部署（需要 root 权限）：

```bash
sudo bash deploy.sh
```

脚本会自动完成以下步骤：

1. 检查运行环境（Python >= 3.11）
2. 安装 uv 包管理器（如未安装）
3. 部署代码到 `/opt/ddns-cf`（可自定义）
4. 创建系统用户 `ddns`
5. 交互式引导生成配置文件
6. 安装并启动 systemd 服务

卸载：

```bash
sudo bash deploy.sh --uninstall
```

## 手动安装

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

完整配置选项见 `examples/config.toml`。

## 运行

单次检查：

```bash
uv run ddns-cf --config /etc/ddns-cf/config.toml --once
```

常驻运行：

```bash
uv run ddns-cf --config /etc/ddns-cf/config.toml
```

通过 `deploy.sh` 部署后，使用 systemd 管理服务：

```bash
systemctl status ddns-cf      # 查看状态
journalctl -u ddns-cf -f      # 查看日志
systemctl restart ddns-cf      # 重启服务
```

## 开发

```bash
uv run ruff format .
uv run ruff check .
uv run ty check .
uv run pytest
```
