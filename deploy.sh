#!/usr/bin/env bash

set -Eeuo pipefail

# =============================================================================
# ddns-cf 部署脚本
# 用法：
#   sudo bash deploy.sh              # 安装 / 更新
#   sudo bash deploy.sh --uninstall  # 卸载
# =============================================================================

INSTALL_DIR="/opt/ddns-cf"
CONFIG_DIR="/etc/ddns-cf"
CONFIG_FILE="${CONFIG_DIR}/config.toml"
INSTALL_CONF="${CONFIG_DIR}/install.conf"
SERVICE_NAME="ddns-cf"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
SERVICE_USER="ddns"
SERVICE_GROUP="ddns"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' BLUE='' BOLD='' RESET=''
fi

info()    { printf "${BLUE}[信息]${RESET} %s\n" "$*"; }
success() { printf "${GREEN}[完成]${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}[警告]${RESET} %s\n" "$*"; }
error()   { printf "${RED}[错误]${RESET} %s\n" "$*" >&2; }
die()     { error "$@"; exit 1; }

confirm() {
    local prompt="$1"
    local default="${2:-Y}"

    local hint
    if [[ "${default}" =~ ^[Yy] ]]; then
        hint="Y/n"
    else
        hint="y/N"
    fi

    local answer
    printf "${BOLD}%s [%s]:${RESET} " "${prompt}" "${hint}"
    read -r answer
    answer="${answer:-${default}}"

    [[ "${answer}" =~ ^[Yy] ]]
}

ask() {
    local prompt="$1"
    local default="${2:-}"

    if [[ -n "${default}" ]]; then
        printf "${BOLD}%s${RESET} [${default}]: " "${prompt}"
    else
        printf "${BOLD}%s:${RESET} " "${prompt}"
    fi
    read -r REPLY
    REPLY="${REPLY:-${default}}"
}

ask_number() {
    local prompt="$1"
    local default="$2"
    local min="${3:-1}"

    while true; do
        ask "${prompt}" "${default}"
        if [[ "${REPLY}" =~ ^[0-9]+$ ]] && [[ "${REPLY}" -ge "${min}" ]]; then
            return
        fi
        warn "请输入一个不小于 ${min} 的整数"
    done
}


ask_secret() {
    local prompt="$1"
    printf "${BOLD}%s:${RESET} " "${prompt}"
    read -rs REPLY
    printf "\n"
}

check_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        die "请使用 root 用户或 sudo 执行此脚本"
    fi
}

check_os() {
    if [[ "$(uname -s)" != "Linux" ]]; then
        die "此脚本仅支持 Linux 系统（当前系统：$(uname -s)）"
    fi
}

check_tty() {
    if [[ ! -t 0 ]]; then
        die "此脚本需要交互式终端运行，请勿通过管道执行"
    fi
}

check_python() {
    local cmd
    for cmd in python3 python; do
        if command -v "${cmd}" >/dev/null 2>&1; then
            local version
            version="$("${cmd}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
            local major minor
            major="${version%%.*}"
            minor="${version#*.}"
            if [[ "${major}" -ge 3 && "${minor}" -ge 11 ]]; then
                PYTHON_BIN="$(command -v "${cmd}")"
                return 0
            fi
        fi
    done
    return 1
}

check_uv() {
    command -v uv >/dev/null 2>&1
}

on_error() {
    local lineno="$1"
    error "脚本在第 ${lineno} 行执行失败"
    error "如需帮助，请检查以上输出或提交 issue"
}
trap 'on_error ${LINENO}' ERR

do_install() {
    printf "\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "${BOLD}  ddns-cf 部署脚本${RESET}\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "\n"

    info "正在检查运行环境..."

    check_root
    check_os
    check_tty

    if check_python; then
        success "Python 已就绪：${PYTHON_BIN}"
    else
        die "未找到 Python >= 3.11，请先安装后再运行此脚本"
    fi

    if check_uv; then
        success "uv 已安装：$(uv --version)"
    else
        warn "未检测到 uv 包管理器"
        if confirm "是否自动安装 uv？"; then
            info "正在安装 uv..."
            curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
            if check_uv; then
                success "uv 安装成功：$(uv --version)"
            else
                die "uv 安装后仍无法找到，请手动安装后重试"
            fi
        else
            die "ddns-cf 依赖 uv 运行，无法继续"
        fi
    fi

    printf "\n"
    info "── 部署代码 ──"

    ask "安装目录" "${INSTALL_DIR}"
    INSTALL_DIR="${REPLY}"

    if [[ -d "${INSTALL_DIR}" ]]; then
        warn "目录 ${INSTALL_DIR} 已存在"
        if confirm "是否更新（覆盖代码文件）？"; then
            info "正在更新 ${INSTALL_DIR} ..."
        else
            info "跳过代码部署，使用现有文件"
            if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
                info "检测到缺少 .venv，正在执行 uv sync..."
                uv sync --directory "${INSTALL_DIR}"
            fi
            step_create_user
            step_permissions
            step_configure
            step_systemd
            step_start
            return
        fi
    else
        info "正在创建目录 ${INSTALL_DIR} ..."
        mkdir -p "${INSTALL_DIR}"
    fi

    cp -a "${SCRIPT_DIR}/." "${INSTALL_DIR}/"
    rm -rf "${INSTALL_DIR}/.git" \
           "${INSTALL_DIR}/.venv" \
           "${INSTALL_DIR}/.pytest_cache" \
           "${INSTALL_DIR}/.ruff_cache"
    find "${INSTALL_DIR}" -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

    success "代码已部署到 ${INSTALL_DIR}"

    info "正在安装 Python 依赖（uv sync）..."
    uv sync --directory "${INSTALL_DIR}" --no-dev
    success "依赖安装完成"

    step_create_user
    step_permissions

    step_configure

    step_systemd

    step_start
}

step_create_user() {
    printf "\n"
    info "── 系统用户 ──"

    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        success "用户 ${SERVICE_USER} 已存在"
    else
        info "正在创建系统用户 ${SERVICE_USER} ..."
        useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
        success "用户 ${SERVICE_USER} 创建完成"
    fi
}

step_permissions() {
    info "正在设置目录权限..."
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_DIR}"
    success "${INSTALL_DIR} 所有权已设置为 ${SERVICE_USER}:${SERVICE_GROUP}"
}

step_configure() {
    printf "\n"
    info "── 配置文件 ──"

    mkdir -p "${CONFIG_DIR}"

    if [[ -f "${CONFIG_FILE}" ]]; then
        warn "配置文件 ${CONFIG_FILE} 已存在"
        if ! confirm "是否重新生成配置？（现有配置将被备份）"; then
            info "保留现有配置，跳过配置引导"
            chown "${SERVICE_USER}:${SERVICE_GROUP}" "${CONFIG_DIR}"
            chmod 700 "${CONFIG_DIR}"
            chown "${SERVICE_USER}:${SERVICE_GROUP}" "${CONFIG_FILE}"
            chmod 600 "${CONFIG_FILE}"
            return
        fi
        local backup="${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
        cp "${CONFIG_FILE}" "${backup}"
        success "已备份到 ${backup}"
    fi

    printf "\n"
    info "接下来将引导你完成配置，直接回车使用 [方括号] 中的默认值。"
    printf "\n"

    printf "${BOLD}── Cloudflare 设置 ──${RESET}\n"
    printf "  API Token 可在 https://dash.cloudflare.com/profile/api-tokens 创建\n"
    printf "  所需权限：Zone > DNS > Edit\n"
    printf "\n"

    local cf_token cf_zone_id

    ask_secret "Cloudflare API Token"
    cf_token="${REPLY}"
    while [[ -z "${cf_token}" ]]; do
        warn "API Token 不能为空"
        ask_secret "Cloudflare API Token"
        cf_token="${REPLY}"
    done

    ask "Cloudflare Zone ID"
    cf_zone_id="${REPLY}"
    while [[ -z "${cf_zone_id}" ]]; do
        warn "Zone ID 不能为空"
        ask "Cloudflare Zone ID"
        cf_zone_id="${REPLY}"
    done

    printf "\n"
    printf "${BOLD}── DNS 记录 ──${RESET}\n"
    printf "  至少需要添加一条 DNS 记录。\n"
    printf "  类型 A = IPv4，AAAA = IPv6。\n"
    printf "\n"

    local records_toml=""
    local record_count=0

    while true; do
        record_count=$((record_count + 1))
        info "--- 记录 #${record_count} ---"

        local rec_name rec_type rec_ttl rec_proxied

        ask "域名（如 example.com 或 sub.example.com）"
        rec_name="${REPLY}"
        while [[ -z "${rec_name}" ]]; do
            warn "域名不能为空"
            ask "域名"
            rec_name="${REPLY}"
        done

        ask "记录类型（A / AAAA）" "A"
        rec_type="${REPLY^^}" 
        while [[ "${rec_type}" != "A" && "${rec_type}" != "AAAA" ]]; do
            warn "类型只能是 A 或 AAAA"
            ask "记录类型（A / AAAA）" "A"
            rec_type="${REPLY^^}"
        done

        ask_number "TTL（1 = 自动）" "1" 1
        rec_ttl="${REPLY}"

        if confirm "是否开启 Cloudflare 代理（proxied）？" "N"; then
            rec_proxied="true"
        else
            rec_proxied="false"
        fi

        records_toml+="
[[records]]
name = \"${rec_name}\"
type = \"${rec_type}\"
ttl = ${rec_ttl}
proxied = ${rec_proxied}
"

        printf "\n"
        if ! confirm "是否继续添加下一条记录？" "N"; then
            break
        fi
        printf "\n"
    done

    printf "\n"
    printf "${BOLD}── 运行时设置 ──${RESET}\n"

    local rt_interval rt_timeout rt_notify_no_change

    ask_number "检查间隔（秒）" "300" 1
    rt_interval="${REPLY}"

    ask_number "HTTP 超时（秒）" "10" 1
    rt_timeout="${REPLY}"

    if confirm "IP 未变化时也发送通知？" "N"; then
        rt_notify_no_change="true"
    else
        rt_notify_no_change="false"
    fi

    printf "\n"
    printf "${BOLD}── IP 检测端点 ──${RESET}\n"

    local ip_v4_ep ip_v6_ep

    ask "IPv4 检测地址" "https://api.ipify.org"
    ip_v4_ep="${REPLY}"

    ask "IPv6 检测地址" "https://api6.ipify.org"
    ip_v6_ep="${REPLY}"

    printf "\n"
    printf "${BOLD}── Telegram 通知（可选）──${RESET}\n"

    local tg_enabled="false"
    local tg_bot_token=""
    local tg_chat_id=""

    if confirm "是否启用 Telegram 通知？" "N"; then
        tg_enabled="true"

        ask "Telegram Bot Token"
        tg_bot_token="${REPLY}"
        while [[ -z "${tg_bot_token}" ]]; do
            warn "Bot Token 不能为空"
            ask "Telegram Bot Token"
            tg_bot_token="${REPLY}"
        done

        ask "Telegram Chat ID"
        tg_chat_id="${REPLY}"
        while [[ -z "${tg_chat_id}" ]]; do
            warn "Chat ID 不能为空"
            ask "Telegram Chat ID"
            tg_chat_id="${REPLY}"
        done
    fi

    cat > "${CONFIG_FILE}" <<EOF
[cloudflare]
api_token = "${cf_token}"
zone_id = "${cf_zone_id}"

[runtime]
interval_seconds = ${rt_interval}
timeout_seconds = ${rt_timeout}
notify_on_no_change = ${rt_notify_no_change}

[ip]
ipv4_endpoint = "${ip_v4_ep}"
ipv6_endpoint = "${ip_v6_ep}"
${records_toml}
[telegram]
enabled = ${tg_enabled}
bot_token = "${tg_bot_token}"
chat_id = "${tg_chat_id}"
EOF

    chown "${SERVICE_USER}:${SERVICE_GROUP}" "${CONFIG_DIR}"
    chmod 700 "${CONFIG_DIR}"
    chown "${SERVICE_USER}:${SERVICE_GROUP}" "${CONFIG_FILE}"
    chmod 600 "${CONFIG_FILE}"

    success "配置文件已写入 ${CONFIG_FILE}"
}

step_systemd() {
    printf "\n"
    info "── systemd 服务 ──"

    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Cloudflare DDNS service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/ddns-cf --config ${CONFIG_FILE}
Restart=always
RestartSec=10
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=${CONFIG_DIR}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    success "systemd 服务已安装：${SERVICE_FILE}"
}

step_start() {
    printf "\n"
    info "── 启动服务 ──"

    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        warn "服务正在运行，将执行重启"
        systemctl restart "${SERVICE_NAME}"
        success "服务已重启"
    else
        if confirm "是否立即启动 ${SERVICE_NAME} 服务？"; then
            systemctl start "${SERVICE_NAME}"
            success "服务已启动"
        fi
    fi

    if confirm "是否设置开机自启？"; then
        systemctl enable "${SERVICE_NAME}"
        success "已设置开机自启"
    fi

    printf "\n"
    if confirm "是否执行一次验证（--once 模式检查配置是否正确）？"; then
        info "正在执行验证..."
        printf "\n"
        if sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/ddns-cf" \
            --config "${CONFIG_FILE}" --once; then
            printf "\n"
            success "验证通过，配置工作正常"
        else
            printf "\n"
            warn "验证未通过，请检查配置文件 ${CONFIG_FILE}"
            warn "可使用以下命令查看日志：journalctl -u ${SERVICE_NAME} -f"
        fi
    fi

    cat > "${INSTALL_CONF}" <<EOF
INSTALL_DIR=${INSTALL_DIR}
CONFIG_DIR=${CONFIG_DIR}
SERVICE_USER=${SERVICE_USER}
SERVICE_GROUP=${SERVICE_GROUP}
EOF
    chmod 600 "${INSTALL_CONF}"

    printf "\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "${GREEN}${BOLD}  部署完成！${RESET}\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "\n"
    info "常用命令："
    printf "  查看状态：  systemctl status %s\n" "${SERVICE_NAME}"
    printf "  查看日志：  journalctl -u %s -f\n" "${SERVICE_NAME}"
    printf "  重启服务：  systemctl restart %s\n" "${SERVICE_NAME}"
    printf "  编辑配置：  sudoedit %s\n" "${CONFIG_FILE}"
    printf "  卸载服务：  sudo bash %s --uninstall\n" "${BASH_SOURCE[0]}"
    printf "\n"
}

do_uninstall() {
    printf "\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "${BOLD}  ddns-cf 卸载${RESET}\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "\n"

    check_root
    check_tty

    if [[ -f "${INSTALL_CONF}" ]]; then
        source "${INSTALL_CONF}"
        info "已从 ${INSTALL_CONF} 读取安装路径"
    else
        warn "未找到 ${INSTALL_CONF}，将使用默认路径"
    fi

    warn "此操作将移除 ddns-cf 服务及相关文件。"
    if ! confirm "确定要继续吗？" "N"; then
        info "已取消"
        exit 0
    fi

    printf "\n"

    if systemctl is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
        info "正在停止服务..."
        systemctl stop "${SERVICE_NAME}"
        success "服务已停止"
    fi

    if systemctl is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
        info "正在禁用开机自启..."
        systemctl disable "${SERVICE_NAME}"
        success "已禁用开机自启"
    fi

    if [[ -f "${SERVICE_FILE}" ]]; then
        rm -f "${SERVICE_FILE}"
        systemctl daemon-reload
        success "已删除 ${SERVICE_FILE}"
    else
        info "服务文件不存在，跳过"
    fi

    if [[ -d "${INSTALL_DIR}" ]]; then
        if confirm "是否删除安装目录 ${INSTALL_DIR}？"; then
            rm -rf "${INSTALL_DIR}"
            success "已删除 ${INSTALL_DIR}"
        else
            info "保留 ${INSTALL_DIR}"
        fi
    fi

    if [[ -d "${CONFIG_DIR}" ]]; then
        if confirm "是否删除配置目录 ${CONFIG_DIR}？（包含 API Token 等敏感信息）"; then
            rm -rf "${CONFIG_DIR}"
            success "已删除 ${CONFIG_DIR}"
        else
            info "保留 ${CONFIG_DIR}"
        fi
    fi

    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        if confirm "是否删除系统用户 ${SERVICE_USER}？" "N"; then
            userdel "${SERVICE_USER}"
            success "已删除用户 ${SERVICE_USER}"
        else
            info "保留用户 ${SERVICE_USER}"
        fi
    fi

    printf "\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "${GREEN}${BOLD}  卸载完成${RESET}\n"
    printf "${BOLD}========================================${RESET}\n"
    printf "\n"
}

main() {
    case "${1:-}" in
        --uninstall | uninstall)
            do_uninstall
            ;;
        --help | -h)
            printf "用法：\n"
            printf "  sudo bash %s              安装 / 更新 ddns-cf\n" "${BASH_SOURCE[0]}"
            printf "  sudo bash %s --uninstall  卸载 ddns-cf\n" "${BASH_SOURCE[0]}"
            ;;
        "")
            do_install
            ;;
        *)
            die "未知参数：${1}，使用 --help 查看用法"
            ;;
    esac
}

main "$@"
