"""Replaceable HTTP transport used by the read-only Azure DevOps client."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..domain import AzureDevOpsCancelledError, AzureDevOpsTimeoutError, AzureDevOpsUnavailableError


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def wait(self, seconds: float) -> bool:
        return self._event.wait(seconds)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    payload: Any = None


class IHttpExecutor(Protocol):
    def execute(self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float, cancellation: CancellationToken | None = None) -> HttpResponse: ...


class UrllibHttpExecutor:
    def execute(self, method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float, cancellation: CancellationToken | None = None) -> HttpResponse:
        if cancellation and cancellation.cancelled:
            raise AzureDevOpsCancelledError()
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = _decode(response.read())
                return HttpResponse(response.status, {key.lower(): value for key, value in response.headers.items()}, payload)
        except urllib.error.HTTPError as error:
            return HttpResponse(error.code, {key.lower(): value for key, value in error.headers.items()}, _decode(error.read()))
        except (TimeoutError, socket.timeout) as error:
            raise AzureDevOpsTimeoutError() from error
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                raise AzureDevOpsTimeoutError() from error
            raise AzureDevOpsUnavailableError() from error


def _decode(value: bytes) -> Any:
    if not value:
        return {}
    text = value.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"message": text}
