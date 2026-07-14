"""Restricted Azure DevOps pull-request comment transport."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlencode

from ..domain import AzureDevOpsAuthorizationError, AzureDevOpsIntegrationError, AzureDevOpsNotFoundError, AzureDevOpsUnavailableError
from .http import IHttpExecutor, UrllibHttpExecutor


class AzureDevOpsPullRequestCommentClient:
    """Can create a comment thread only; it cannot approve, complete, or merge a PR."""

    def __init__(self, connection, credential_provider, *, correlation_id: str = "", executor: IHttpExecutor | None = None, timeout_seconds: float = 15) -> None:
        self._connection = connection
        self._credentials = credential_provider
        self._correlation_id = correlation_id
        self._executor = executor or UrllibHttpExecutor()
        self._timeout = timeout_seconds

    def add_comment(self, project: str, repository_id: str, pull_request_id: int, comment: str) -> dict[str, Any]:
        path = f"/{quote(project, safe='')}/_apis/git/repositories/{quote(repository_id, safe='')}/pullRequests/{pull_request_id}/threads"
        url = f"{self._connection.organization_url}{path}?{urlencode({'api-version': '7.1'})}"
        payload = {"comments": [{"parentCommentId": 0, "content": comment, "commentType": 1}], "status": 1}
        headers = {"Accept": "application/json", "Content-Type": "application/json", "X-Correlation-ID": self._correlation_id}
        headers.update(self._credentials.authorization_headers(self._connection, self._correlation_id))
        response = self._executor.execute("POST", url, headers, json.dumps(payload).encode("utf-8"), self._timeout, None)
        if response.status >= 400:
            raise _error(response.status, response.payload, self._correlation_id)
        return response.payload if isinstance(response.payload, dict) else {}


def _error(status: int, payload: Any, correlation_id: str) -> AzureDevOpsIntegrationError:
    message = str(payload.get("message") or "") if isinstance(payload, dict) else ""
    if status == 403:
        return AzureDevOpsAuthorizationError(message or "Azure DevOps pull-request comment permission was denied.", status=status, correlation_id=correlation_id)
    if status == 404:
        return AzureDevOpsNotFoundError(message or "Azure DevOps pull request was not found.", status=status, correlation_id=correlation_id)
    return AzureDevOpsUnavailableError(message or "Azure DevOps pull-request comment failed.", status=status, correlation_id=correlation_id)
