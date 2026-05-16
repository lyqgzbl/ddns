from __future__ import annotations

from ddns_cf.config import TelegramConfig
from ddns_cf.http import HttpClient


class TelegramNotifier:
    def __init__(self, http: HttpClient, config: TelegramConfig, *, timeout: float) -> None:
        self._http = http
        self._config = config
        self._timeout = timeout

    def send(self, message: str) -> None:
        if not self._config.usable:
            return

        url = f"https://api.telegram.org/bot{self._config.bot_token}/sendMessage"
        self._http.request(
            "POST",
            url,
            form_body={
                "chat_id": self._config.chat_id,
                "text": message,
                "disable_web_page_preview": "true",
            },
            timeout=self._timeout,
        )
