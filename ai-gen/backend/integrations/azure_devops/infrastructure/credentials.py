"""Secure credential resolution for Azure DevOps clients."""

from __future__ import annotations

import base64
import os
import re
from typing import Protocol

from ..domain import (
    AzureDevOpsAuthenticationError,
    AzureDevOpsAuthenticationMode,
    AzureDevOpsConnection,
)


class ISecretProvider(Protocol):
    def get_secret(self, reference: str) -> str: ...


class EnvironmentSecretProvider:
    """Resolves a secret reference from process configuration without persisting it."""

    _REFERENCE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def get_secret(self, reference: str) -> str:
        if not self._REFERENCE.fullmatch(reference or ""):
            raise AzureDevOpsAuthenticationError("The Azure DevOps secret reference is invalid.")
        value = os.getenv(reference, "")
        if not value:
            raise AzureDevOpsAuthenticationError("The configured Azure DevOps credential is unavailable.")
        return value


class EnvironmentAzureDevOpsCredentialProvider:
    def __init__(self, secret_provider: ISecretProvider | None = None) -> None:
        self._secrets = secret_provider or EnvironmentSecretProvider()

    def authorization_headers(self, connection: AzureDevOpsConnection, correlation_id: str = "") -> dict[str, str]:
        if connection.authentication_mode != AzureDevOpsAuthenticationMode.PAT.value:
            raise AzureDevOpsAuthenticationError(
                f"Authentication mode '{connection.authentication_mode}' is reserved for a future credential provider.",
                correlation_id=correlation_id,
            )
        secret = self._secrets.get_secret(connection.secret_reference)
        encoded = base64.b64encode(f":{secret}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
