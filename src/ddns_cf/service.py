from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass

from ddns_cf.cloudflare import CloudflareClient
from ddns_cf.config import AppConfig, DnsRecordConfig
from ddns_cf.http import HttpClient
from ddns_cf.ip import fetch_ips
from ddns_cf.telegram import TelegramNotifier

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordResult:
    name: str
    type: str
    status: str
    message: str


class DdnsService:
    def __init__(self, config: AppConfig, http: HttpClient | None = None) -> None:
        self._config = config
        self._http = http or HttpClient()
        self._cloudflare = CloudflareClient(
            self._http,
            config.cloudflare,
            timeout=config.runtime.timeout_seconds,
        )
        self._notifier = TelegramNotifier(
            self._http,
            config.telegram,
            timeout=config.runtime.timeout_seconds,
        )
        self._stop = False

    def run_forever(self) -> None:
        self._install_signal_handlers()
        while not self._stop:
            self.run_once()
            self._sleep_until_next_tick()

    def run_once(self) -> list[RecordResult]:
        ips = fetch_ips(self._http, self._config.ip, self._config.runtime.timeout_seconds)
        if not ips:
            message = "DDNS failed: no valid public IPv4 or IPv6 address was fetched"
            LOGGER.error(message)
            self._notify(message)
            return [RecordResult(name="-", type="-", status="failed", message=message)]

        results = [
            self._sync_record(record, ips.get(record.type)) for record in self._config.records
        ]
        for result in results:
            log = (
                LOGGER.info
                if result.status in {"created", "updated", "unchanged"}
                else LOGGER.error
            )
            log("%s %s %s: %s", result.type, result.name, result.status, result.message)
        return results

    def _sync_record(self, record: DnsRecordConfig, target_ip: str | None) -> RecordResult:
        if target_ip is None:
            return RecordResult(
                name=record.name,
                type=record.type,
                status="skipped",
                message=f"no valid public IP for {record.type}",
            )

        try:
            existing = self._cloudflare.find_record(record)
            if existing is None:
                created = self._cloudflare.create_record(record, target_ip)
                message = f"created {record.type} {record.name} -> {created.content}"
                self._notify(f"DDNS success: {message}")
                return RecordResult(record.name, record.type, "created", message)

            if existing.content == target_ip:
                message = f"{record.type} {record.name} already points to {target_ip}"
                if self._config.runtime.notify_on_no_change:
                    self._notify(f"DDNS no change: {message}")
                return RecordResult(record.name, record.type, "unchanged", message)

            updated = self._cloudflare.update_record(existing, record, target_ip)
            message = (
                f"updated {record.type} {record.name}: {existing.content} -> {updated.content}"
            )
            self._notify(f"DDNS success: {message}")
            return RecordResult(record.name, record.type, "updated", message)
        except Exception as error:
            message = f"{record.type} {record.name} failed: {error}"
            self._notify(f"DDNS failed: {message}")
            return RecordResult(record.name, record.type, "failed", message)

    def _notify(self, message: str) -> None:
        try:
            self._notifier.send(message)
        except Exception:
            LOGGER.exception("failed to send Telegram notification")

    def _sleep_until_next_tick(self) -> None:
        deadline = time.monotonic() + self._config.runtime.interval_seconds
        while not self._stop and time.monotonic() < deadline:
            time.sleep(min(1, deadline - time.monotonic()))

    def _install_signal_handlers(self) -> None:
        def stop(_signum: int, _frame: object) -> None:
            self._stop = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
