from __future__ import annotations

import pytest

from ddns_cf.config import ConfigError, parse_config


def test_parse_config_with_multiple_records() -> None:
    config = parse_config(
        {
            "cloudflare": {"api_token": "token", "zone_id": "zone"},
            "records": [
                {"name": "example.com", "type": "A"},
                {"name": "example.com", "type": "aaaa", "ttl": 120, "proxied": True},
            ],
            "telegram": {"enabled": True, "bot_token": "bot", "chat_id": "chat"},
        }
    )

    assert config.cloudflare.api_token == "token"
    assert config.records[0].type == "A"
    assert config.records[1].type == "AAAA"
    assert config.records[1].ttl == 120
    assert config.records[1].proxied is True
    assert config.telegram.usable is True


def test_parse_config_rejects_invalid_record_type() -> None:
    with pytest.raises(ConfigError, match="type must be A or AAAA"):
        parse_config(
            {
                "cloudflare": {"api_token": "token", "zone_id": "zone"},
                "records": [{"name": "example.com", "type": "TXT"}],
            }
        )
