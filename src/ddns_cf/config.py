from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

RecordType = Literal["A", "AAAA"]


@dataclass(frozen=True)
class CloudflareConfig:
    api_token: str
    zone_id: str


@dataclass(frozen=True)
class RuntimeConfig:
    interval_seconds: int = 300
    timeout_seconds: float = 10
    notify_on_no_change: bool = False


@dataclass(frozen=True)
class IpConfig:
    ipv4_endpoint: str = "https://api.ipify.org"
    ipv6_endpoint: str = "https://api6.ipify.org"


@dataclass(frozen=True)
class DnsRecordConfig:
    name: str
    type: RecordType
    ttl: int = 1
    proxied: bool = False


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""

    @property
    def usable(self) -> bool:
        return self.enabled and bool(self.bot_token and self.chat_id)


@dataclass(frozen=True)
class AppConfig:
    cloudflare: CloudflareConfig
    runtime: RuntimeConfig
    ip: IpConfig
    records: tuple[DnsRecordConfig, ...]
    telegram: TelegramConfig


class ConfigError(ValueError):
    """Raised when the config file is invalid."""


def load_config(path: Path) -> AppConfig:
    with path.open("rb") as file:
        raw = tomllib.load(file)
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> AppConfig:
    cloudflare = _mapping(raw, "cloudflare")
    api_token = _required_str(cloudflare, "api_token", "cloudflare")
    zone_id = _required_str(cloudflare, "zone_id", "cloudflare")

    runtime_raw = _optional_mapping(raw, "runtime")
    runtime = RuntimeConfig(
        interval_seconds=_positive_int(runtime_raw, "interval_seconds", 300, "runtime"),
        timeout_seconds=float(_positive_int(runtime_raw, "timeout_seconds", 10, "runtime")),
        notify_on_no_change=bool(runtime_raw.get("notify_on_no_change", False)),
    )

    ip_raw = _optional_mapping(raw, "ip")
    ip = IpConfig(
        ipv4_endpoint=str(ip_raw.get("ipv4_endpoint", IpConfig.ipv4_endpoint)),
        ipv6_endpoint=str(ip_raw.get("ipv6_endpoint", IpConfig.ipv6_endpoint)),
    )

    records_raw = raw.get("records")
    if not isinstance(records_raw, list) or not records_raw:
        msg = "records must contain at least one [[records]] item"
        raise ConfigError(msg)

    records = tuple(_parse_record(item, index) for index, item in enumerate(records_raw, start=1))

    telegram_raw = _optional_mapping(raw, "telegram")
    telegram = TelegramConfig(
        enabled=bool(telegram_raw.get("enabled", False)),
        bot_token=str(telegram_raw.get("bot_token", "")),
        chat_id=str(telegram_raw.get("chat_id", "")),
    )

    return AppConfig(
        cloudflare=CloudflareConfig(api_token=api_token, zone_id=zone_id),
        runtime=runtime,
        ip=ip,
        records=records,
        telegram=telegram,
    )


def _parse_record(raw: Any, index: int) -> DnsRecordConfig:
    section = f"records[{index}]"
    if not isinstance(raw, dict):
        msg = f"{section} must be a table"
        raise ConfigError(msg)

    name = _required_str(raw, "name", section)
    record_type_raw = _required_str(raw, "type", section).upper()
    if record_type_raw not in {"A", "AAAA"}:
        msg = f"{section}.type must be A or AAAA"
        raise ConfigError(msg)
    record_type = cast(RecordType, record_type_raw)

    return DnsRecordConfig(
        name=name,
        type=record_type,
        ttl=_positive_int(raw, "ttl", 1, section),
        proxied=bool(raw.get("proxied", False)),
    )


def _mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        msg = f"{key} section is required"
        raise ConfigError(msg)
    return value


def _optional_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    if not isinstance(value, dict):
        msg = f"{key} section must be a table"
        raise ConfigError(msg)
    return value


def _required_str(raw: dict[str, Any], key: str, section: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{section}.{key} is required"
        raise ConfigError(msg)
    return value.strip()


def _positive_int(raw: dict[str, Any], key: str, default: int, section: str) -> int:
    value = raw.get(key, default)
    if not isinstance(value, int) or value <= 0:
        msg = f"{section}.{key} must be a positive integer"
        raise ConfigError(msg)
    return value
