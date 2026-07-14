"""Restricted Azure DevOps work-item writer used only by approved automation."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlencode

from ..domain import (
    AzureDevOpsAuthenticationError, AzureDevOpsAuthorizationError,
    AzureDevOpsIntegrationError, AzureDevOpsNotFoundError,
    AzureDevOpsRateLimitError, AzureDevOpsUnavailableError,
)
from .http import IHttpExecutor, UrllibHttpExecutor


class AzureDevOpsWorkItemWriteClient:
    """Exposes only the mutations supported by the HEI command allow-list."""

    def __init__(self, connection, credential_provider, *, correlation_id: str = "", executor: IHttpExecutor | None = None, timeout_seconds: float = 15) -> None:
        self._connection = connection
        self._credentials = credential_provider
        self._correlation_id = correlation_id
        self._executor = executor or UrllibHttpExecutor()
        self._timeout = timeout_seconds

    def create_work_item(self, project: str, work_item_type: str, fields: dict[str, Any]) -> dict[str, Any]:
        operations = [{"op": "add", "path": f"/fields/{name}", "value": value} for name, value in fields.items()]
        return self._request("POST", f"/{quote(project, safe='')}/_apis/wit/workitems/${quote(work_item_type, safe='')}", operations, content_type="application/json-patch+json")

    def update_work_item(self, project: str, work_item_id: int, fields: dict[str, Any], *, expected_revision: int) -> dict[str, Any]:
        operations = [{"op": "add", "path": f"/fields/{name}", "value": value} for name, value in fields.items()]
        return self._request("PATCH", f"/{quote(project, safe='')}/_apis/wit/workitems/{work_item_id}", operations, content_type="application/json-patch+json", expected_revision=expected_revision)

    def link_parent_child(self, project: str, parent_id: int, child_id: int, *, expected_revision: int) -> dict[str, Any]:
        parent_url = f"{self._connection.organization_url}/{quote(project, safe='')}/_apis/wit/workItems/{parent_id}"
        operation = [{"op": "add", "path": "/relations/-", "value": {"rel": "System.LinkTypes.Hierarchy-Reverse", "url": parent_url, "attributes": {"comment": "Linked by approved HEI automation"}}}]
        return self._request("PATCH", f"/{quote(project, safe='')}/_apis/wit/workitems/{child_id}", operation, content_type="application/json-patch+json", expected_revision=expected_revision)

    def add_comment(self, project: str, work_item_id: int, comment: str) -> dict[str, Any]:
        return self._request("POST", f"/{quote(project, safe='')}/_apis/wit/workItems/{work_item_id}/comments", {"text": comment})

    def _request(self, method: str, path: str, payload: Any, *, content_type: str = "application/json", expected_revision: int | None = None) -> dict[str, Any]:
        if method not in {"POST", "PATCH"}:
            raise ValueError("AzureDevOpsWorkItemWriteClient only supports approved POST and PATCH operations.")
        url = f"{self._connection.organization_url}{path}?{urlencode({'api-version': '7.1'})}"
        headers = {"Accept": "application/json", "Content-Type": content_type, "X-Correlation-ID": self._correlation_id}
        if expected_revision is not None:
            headers["If-Match"] = str(expected_revision)
        headers.update(self._credentials.authorization_headers(self._connection, self._correlation_id))
        response = self._executor.execute(method, url, headers, json.dumps(payload).encode("utf-8"), self._timeout, None)
        if response.status >= 400:
            raise _write_error(response.status, response.payload, self._correlation_id)
        return response.payload if isinstance(response.payload, dict) else {}


def _write_error(status: int, payload: Any, correlation_id: str) -> AzureDevOpsIntegrationError:
    message = str(payload.get("message") or payload.get("error", {}).get("message") or "") if isinstance(payload, dict) else ""
    kwargs = {"status": status, "correlation_id": correlation_id}
    if status == 401: return AzureDevOpsAuthenticationError(message or "Azure DevOps credentials were rejected.", **kwargs)
    if status == 403: return AzureDevOpsAuthorizationError(message or "Azure DevOps work-item permission was denied.", **kwargs)
    if status == 404: return AzureDevOpsNotFoundError(message or "Azure DevOps work item was not found.", **kwargs)
    if status == 429: return AzureDevOpsRateLimitError(message or "Azure DevOps rate limit was exceeded.", **kwargs)
    return AzureDevOpsUnavailableError(message or "Azure DevOps work-item write failed.", **kwargs)
