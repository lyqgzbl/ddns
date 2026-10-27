from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from ddns_cf.config import IpConfig
from ddns_cf.http import HttpClient
from ddns_cf.ip import fetch_interface_ipv6, fetch_ips


def _address(value: str, **flags: Any) -> dict[str, Any]:
    return {
        "family": "inet6",
        "scope": "global",
        "local": value,
        "preferred_life_time": 3600,
        **flags,
    }


def _mock_addresses(monkeypatch: pytest.MonkeyPatch, addresses: list[dict[str, Any]]) -> None:
    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        assert args == ["ip", "-j", "-6", "address", "show", "dev", "wlan0"]
        assert kwargs["timeout"] == 10
        data = [{"ifname": "wlan0", "addr_info": addresses}]
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(data))

    monkeypatch.setattr("ddns_cf.ip.subprocess.run", run)


@pytest.mark.parametrize(
    "flags",
    [
        {"temporary": True},
        {"deprecated": True},
        {"tentative": True},
        {"dadfailed": True},
        {"flags": ["temporary"]},
        {"preferred_life_time": 0},
        {"valid_life_time": 0},
    ],
)
def test_ignores_unusable_addresses(monkeypatch: pytest.MonkeyPatch, flags: dict[str, Any]) -> None:
    _mock_addresses(
        monkeypatch,
        [
            _address("2606:4700::1"),
            _address("2606:4700::2", **flags),
            _address("fe80::1"),
            _address("fd00::1"),
            _address("2001:db8::1"),
        ],
    )
    assert fetch_interface_ipv6("wlan0", 10) == "2606:4700::1"


@pytest.mark.parametrize("addresses", [[], [_address("2606:4700::1"), _address("2606:4700::2")]])
def test_missing_or_ambiguous_addresses_never_fall_back_to_api(
    monkeypatch: pytest.MonkeyPatch, addresses: list[dict[str, Any]]
) -> None:
    _mock_addresses(monkeypatch, addresses)

    class NoNetwork(HttpClient):
        def request(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("interface-only mode must not call an IP lookup API")

    assert fetch_ips(NoNetwork(), IpConfig(ipv6_interface="wlan0"), 10, record_types={"AAAA"}) == {}


@pytest.mark.parametrize(
    "error",
    [
        FileNotFoundError(),
        subprocess.TimeoutExpired("ip", 10),
        subprocess.CalledProcessError(1, "ip"),
    ],
)
def test_interface_command_failures_skip_update(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def run(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr("ddns_cf.ip.subprocess.run", run)
    assert fetch_interface_ipv6("wlan0", 10) is None
