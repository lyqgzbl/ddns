from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from ddns_cf.config import CloudflareConfig, DnsRecordConfig
from ddns_cf.http import HttpClient


@dataclass(frozen=True)
class CloudflareRecord:
    id: str
    name: str
    type: str
    content: str


class CloudflareClient:
    def __init__(
        self,
        http: HttpClient,
        config: CloudflareConfig,
        *,
        timeout: float,
        base_url: str = "https://api.cloudflare.com/client/v4",
    ) -> None:
        self._http = http
        self._config = config
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")

    def find_record(self, record: DnsRecordConfig) -> CloudflareRecord | None:
        name = quote(record.name, safe="")
        record_type = quote(record.type, safe="")
        url = (
            f"{self._base_url}/zones/{self._config.zone_id}/dns_records"
            f"?type={record_type}&name={name}&per_page=1"
        )
        payload = self._request_json("GET", url)
        result = _first_result(payload)
        if result is None:
            return None
        return CloudflareRecord(
            id=str(result["id"]),
            name=str(result["name"]),
            type=str(result["type"]),
            content=str(result["content"]),
        )

    def create_record(self, record: DnsRecordConfig, content: str) -> CloudflareRecord:
        url = f"{self._base_url}/zones/{self._config.zone_id}/dns_records"
        payload = self._request_json("POST", url, json_body=_record_body(record, content))
        result = payload["result"]
        return CloudflareRecord(
            id=str(result["id"]),
            name=str(result["name"]),
            type=str(result["type"]),
            content=str(result["content"]),
        )

    def update_record(
        self, existing: CloudflareRecord, record: DnsRecordConfig, content: str
    ) -> CloudflareRecord:
        url = f"{self._base_url}/zones/{self._config.zone_id}/dns_records/{existing.id}"
        payload = self._request_json("PUT", url, json_body=_record_body(record, content))
        result = payload["result"]
        return CloudflareRecord(
            id=str(result["id"]),
            name=str(result["name"]),
            type=str(result["type"]),
            content=str(result["content"]),
        )

    def _request_json(
        self, method: str, url: str, *, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = self._http.request(
            method,
            url,
            headers={"Authorization": f"Bearer {self._config.api_token}"},
            json_body=json_body,
            timeout=self._timeout,
        )
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is not True:
            msg = f"Cloudflare API request failed: {payload}"
            raise RuntimeError(msg)
        return payload


def _record_body(record: DnsRecordConfig, content: str) -> dict[str, Any]:
    return {
        "type": record.type,
        "name": record.name,
        "content": content,
        "ttl": record.ttl,
        "proxied": record.proxied,
    }


def _first_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    result = payload.get("result")
    if not isinstance(result, list) or not result:
        return None
    first = result[0]
    if not isinstance(first, dict):
        return None
    return first
