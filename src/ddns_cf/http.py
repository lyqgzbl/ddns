from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class HttpError(RuntimeError):
    """Raised when an HTTP request fails."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8").strip()

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class HttpClient:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        form_body: dict[str, str] | None = None,
        timeout: float = 10,
    ) -> HttpResponse:
        body: bytes | None = None
        request_headers = dict(headers or {})

        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif form_body is not None:
            body = urlencode(form_body).encode("utf-8")
            request_headers["Content-Type"] = "application/x-www-form-urlencoded"

        request = Request(url, data=body, headers=request_headers, method=method.upper())
        try:
            with urlopen(request, timeout=timeout) as response:
                return HttpResponse(status=response.status, body=response.read())
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            msg = f"HTTP {error.code} for {url}: {detail}"
            raise HttpError(msg) from error
        except URLError as error:
            msg = f"HTTP request failed for {url}: {error.reason}"
            raise HttpError(msg) from error
