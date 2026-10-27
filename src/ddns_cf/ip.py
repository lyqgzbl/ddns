from __future__ import annotations

import json
import logging
import subprocess
from ipaddress import IPv4Address, IPv6Address, ip_address

from ddns_cf.config import IpConfig
from ddns_cf.http import HttpClient

LOGGER = logging.getLogger(__name__)


def fetch_ips(
    client: HttpClient,
    config: IpConfig,
    timeout: float,
    *,
    record_types: set[str] | None = None,
) -> dict[str, str]:
    if record_types is None:
        record_types = {"A", "AAAA"}
    ips: dict[str, str] = {}
    if "A" in record_types:
        ipv4 = fetch_ip(client, config.ipv4_endpoint, timeout, 4)
        if ipv4 is not None:
            ips["A"] = ipv4
    if "AAAA" in record_types:
        if config.ipv6_interface:
            ipv6 = fetch_interface_ipv6(config.ipv6_interface, timeout)
        else:
            ipv6 = fetch_ip(client, config.ipv6_endpoint, timeout, 6)
        if ipv6 is not None:
            ips["AAAA"] = ipv6
    return ips


def fetch_interface_ipv6(interface: str, timeout: float) -> str | None:
    """Select one usable public IPv6; never fall back to an external lookup API."""
    try:
        result = subprocess.run(
            ["ip", "-j", "-6", "address", "show", "dev", interface],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        interfaces = json.loads(result.stdout)
        candidates: set[str] = set()
        for item in interfaces:
            if item.get("ifname") != interface:
                continue
            for address in item.get("addr_info", []):
                if address.get("family") != "inet6" or address.get("scope") != "global":
                    continue
                excluded = ("temporary", "deprecated", "tentative", "dadfailed")
                if any(address.get(flag) or flag in address.get("flags", []) for flag in excluded):
                    continue
                if address.get("preferred_life_time") == 0 or address.get("valid_life_time") == 0:
                    continue
                parsed = IPv6Address(address["local"])
                if parsed.is_global:
                    candidates.add(str(parsed))
        if len(candidates) == 1:
            return candidates.pop()
        LOGGER.error("interface %s has %d usable public IPv6 addresses", interface, len(candidates))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError):
        LOGGER.error("failed to read IPv6 addresses from interface %s", interface)
    return None


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
