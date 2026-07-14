from __future__ import annotations

from .client import AzureDevOpsReadClient
from .credentials import EnvironmentAzureDevOpsCredentialProvider
from .pr_comment_client import AzureDevOpsPullRequestCommentClient
from .write_client import AzureDevOpsWorkItemWriteClient


class AzureDevOpsClientFactory:
    def __init__(self, credential_provider=None, **client_options) -> None:
        self._credentials = credential_provider or EnvironmentAzureDevOpsCredentialProvider()
        self._options = client_options

    def create(self, connection, *, correlation_id: str = "") -> AzureDevOpsReadClient:
        return AzureDevOpsReadClient(connection, self._credentials, correlation_id=correlation_id, **self._options)

    def create_writer(self, connection, *, correlation_id: str = "") -> AzureDevOpsWorkItemWriteClient:
        return AzureDevOpsWorkItemWriteClient(connection, self._credentials, correlation_id=correlation_id, **self._options)

    def create_pull_request_comment_writer(self, connection, *, correlation_id: str = "") -> AzureDevOpsPullRequestCommentClient:
        return AzureDevOpsPullRequestCommentClient(connection, self._credentials, correlation_id=correlation_id, **self._options)
