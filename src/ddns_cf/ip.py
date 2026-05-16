from __future__ import annotations

from ipaddress import IPv4Address, IPv6Address, ip_address

from ddns_cf.config import IpConfig
from ddns_cf.http import HttpClient


def fetch_ips(client: HttpClient, config: IpConfig, timeout: float) -> dict[str, str]:
    ips: dict[str, str] = {}
    ipv4 = fetch_ip(client, config.ipv4_endpoint, timeout, 4)
    ipv6 = fetch_ip(client, config.ipv6_endpoint, timeout, 6)

    if ipv4 is not None:
        ips["A"] = ipv4
    if ipv6 is not None:
        ips["AAAA"] = ipv6
    return ips


def fetch_ip(client: HttpClient, endpoint: str, timeout: float, version: int) -> str | None:
    try:
        value = client.request("GET", endpoint, timeout=timeout).text()
    except Exception:
        return None

    try:
        parsed = ip_address(value)
    except ValueError:
        return None

    if version == 4 and isinstance(parsed, IPv4Address):
        return str(parsed)
    if version == 6 and isinstance(parsed, IPv6Address):
        return str(parsed)
    return None
