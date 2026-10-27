from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs, urlparse

from ddns_cf.config import (
    AppConfig,
    CloudflareConfig,
    DnsRecordConfig,
    IpConfig,
    RuntimeConfig,
    TelegramConfig,
)
from ddns_cf.http import HttpClient, HttpResponse
from ddns_cf.service import DdnsService


class FakeHttp(HttpClient):
    def __init__(self, *, ipv4: str = "203.0.113.10", ipv6: str = "2001:db8::10") -> None:
        self.ipv4 = ipv4
        self.ipv6 = ipv6
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.requests: list[tuple[str, str, dict[str, Any] | None, dict[str, str] | None]] = []
        self.telegram_messages: list[str] = []
        self.last_proxy: str | None = None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        form_body: dict[str, str] | None = None,
        timeout: float = 10,
        proxy: str = "",
    ) -> HttpResponse:
        del headers, timeout
        self.requests.append((method, url, json_body, form_body))
        if "api.telegram.org" in url:
            self.last_proxy = proxy

        if url == "https://ipv4.test":
            return HttpResponse(200, self.ipv4.encode())
        if url == "https://ipv6.test":
            return HttpResponse(200, self.ipv6.encode())
        if "api.telegram.org" in url:
            assert form_body is not None
            self.telegram_messages.append(form_body["text"])
            return _json_response({"ok": True})

        parsed = urlparse(url)
        if parsed.path.endswith("/dns_records") and method == "GET":
            query = parse_qs(parsed.query)
            key = (query["type"][0], query["name"][0])
            record = self.records.get(key)
            return _json_response({"success": True, "result": [] if record is None else [record]})

        if parsed.path.endswith("/dns_records") and method == "POST":
            assert json_body is not None
            record = {
                "id": f"{json_body['type']}-{json_body['name']}",
                "type": json_body["type"],
                "name": json_body["name"],
                "content": json_body["content"],
            }
            self.records[(record["type"], record["name"])] = record
            return _json_response({"success": True, "result": record})

        if "/dns_records/" in parsed.path and method == "PUT":
            assert json_body is not None
            record = {
                "id": parsed.path.rsplit("/", 1)[1],
                "type": json_body["type"],
                "name": json_body["name"],
                "content": json_body["content"],
            }
            self.records[(record["type"], record["name"])] = record
            return _json_response({"success": True, "result": record})

        raise AssertionError(f"unexpected request: {method} {url}")


def test_updates_changed_ipv4_record_and_notifies() -> None:
    http = FakeHttp()
    http.records[("A", "example.com")] = {
        "id": "record-1",
        "type": "A",
        "name": "example.com",
        "content": "198.51.100.1",
    }

    result = DdnsService(_config(), http).run_once()

    assert result[0].status == "updated"
    assert http.records[("A", "example.com")]["content"] == "203.0.113.10"
    assert http.telegram_messages == [
        "DDNS success: updated A example.com: 198.51.100.1 -> 203.0.113.10"
    ]


def test_updates_ipv6_record() -> None:
    config = replace(_config(), records=(DnsRecordConfig(name="example.com", type="AAAA"),))
    http = FakeHttp()
    http.records[("AAAA", "example.com")] = {
        "id": "record-1",
        "type": "AAAA",
        "name": "example.com",
        "content": "2001:db8::1",
    }

    result = DdnsService(config, http).run_once()

    assert result[0].status == "updated"
    assert http.records[("AAAA", "example.com")]["content"] == "2001:db8::10"


def test_unchanged_record_does_not_update_or_notify() -> None:
    http = FakeHttp()
    http.records[("A", "example.com")] = {
        "id": "record-1",
        "type": "A",
        "name": "example.com",
        "content": "203.0.113.10",
    }

    result = DdnsService(_config(), http).run_once()

    assert result[0].status == "unchanged"
    assert _method_count(http, "PUT") == 0
    assert http.telegram_messages == []


def test_creates_missing_record() -> None:
    http = FakeHttp()

    result = DdnsService(_config(), http).run_once()

    assert result[0].status == "created"
    assert http.records[("A", "example.com")]["content"] == "203.0.113.10"
    assert http.telegram_messages == ["DDNS success: created A example.com -> 203.0.113.10"]


def test_telegram_disabled_skips_notification() -> None:
    config = replace(_config(), telegram=TelegramConfig(enabled=False))
    http = FakeHttp()

    result = DdnsService(config, http).run_once()

    assert result[0].status == "created"
    assert http.telegram_messages == []


def test_telegram_proxy_passed_to_http_client() -> None:
    config = replace(
        _config(),
        telegram=TelegramConfig(
            enabled=True, bot_token="bot", chat_id="chat", proxy="http://127.0.0.1:7890"
        ),
    )
    http = FakeHttp()

    DdnsService(config, http).run_once()

    assert http.last_proxy == "http://127.0.0.1:7890"


def test_interface_only_ipv6_skips_all_ip_lookup_apis(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "ddns_cf.ip.fetch_interface_ipv6", lambda interface, timeout: "2606:4700::1"
    )
    config = replace(
        _config(),
        ip=IpConfig(ipv6_interface="wlan0"),
        records=(DnsRecordConfig(name="git.example.com", type="AAAA", ttl=120),),
    )
    http = FakeHttp()

    result = DdnsService(config, http).run_once()

    assert result[0].status == "created"
    assert http.records[("AAAA", "git.example.com")]["content"] == "2606:4700::1"
    assert all("ipify.org" not in request[1] for request in http.requests)


def test_ipv4_only_records_skip_ipv6_lookup() -> None:
    http = FakeHttp()
    DdnsService(_config(), http).run_once()
    assert not any(request[1] == "https://ipv6.test" for request in http.requests)


def test_dry_run_never_writes_or_sends_notifications() -> None:
    for current_ip in [None, "198.51.100.1", "203.0.113.10"]:
        http = FakeHttp()
        if current_ip is not None:
            http.records[("A", "example.com")] = {
                "id": "record-1",
                "type": "A",
                "name": "example.com",
                "content": current_ip,
            }
        result = DdnsService(_config(), http).run_once(dry_run=True)
        assert result[0].status == "planned"
        assert all(request[0] == "GET" for request in http.requests)
        assert http.telegram_messages == []


def test_dry_run_failure_does_not_notify() -> None:
    http = FakeHttp(ipv4="invalid")
    result = DdnsService(_config(), http).run_once(dry_run=True)
    assert result[0].status == "failed"
    assert http.telegram_messages == []
    assert not any("dns_records" in request[1] for request in http.requests)


def test_record_settings_are_corrected_even_when_address_is_unchanged() -> None:
    http = FakeHttp()
    http.records[("A", "example.com")] = {
        "id": "record-1",
        "type": "A",
        "name": "example.com",
        "content": http.ipv4,
        "ttl": 600,
        "proxied": True,
    }
    result = DdnsService(_config(), http).run_once()
    assert result[0].status == "updated"
    update = next(request[2] for request in http.requests if request[0] == "PUT")
    assert update is not None
    assert update["ttl"] == 1
    assert update["proxied"] is False


def _config() -> AppConfig:
    return AppConfig(
        cloudflare=CloudflareConfig(api_token="token", zone_id="zone"),
        runtime=RuntimeConfig(interval_seconds=300, timeout_seconds=10),
        ip=IpConfig(ipv4_endpoint="https://ipv4.test", ipv6_endpoint="https://ipv6.test"),
        records=(DnsRecordConfig(name="example.com", type="A"),),
        telegram=TelegramConfig(enabled=True, bot_token="bot", chat_id="chat"),
    )


def _json_response(payload: dict[str, Any]) -> HttpResponse:
    return HttpResponse(200, json.dumps(payload).encode())


def _method_count(http: FakeHttp, method: str) -> int:
    return sum(1 for request in http.requests if request[0] == method)
