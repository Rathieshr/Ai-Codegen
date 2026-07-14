"""Typed Azure DevOps integration failures."""

from __future__ import annotations


class AzureDevOpsIntegrationError(Exception):
    def __init__(self, message: str, *, code: str = "azure_devops_error", status: int | None = None, retryable: bool = False, correlation_id: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.status = status
        self.retryable = retryable
        self.correlation_id = correlation_id


class AzureDevOpsAuthenticationError(AzureDevOpsIntegrationError):
    def __init__(self, message: str = "Azure DevOps authentication failed.", **kwargs) -> None:
        super().__init__(message, code="authentication_failed", retryable=False, **kwargs)


class AzureDevOpsAuthorizationError(AzureDevOpsIntegrationError):
    def __init__(self, message: str = "Azure DevOps authorization failed.", **kwargs) -> None:
        super().__init__(message, code="authorization_failed", retryable=False, **kwargs)


class AzureDevOpsUnavailableError(AzureDevOpsIntegrationError):
    def __init__(self, message: str = "Azure DevOps is unavailable.", **kwargs) -> None:
        super().__init__(message, code="organization_unavailable", retryable=True, **kwargs)


class AzureDevOpsRateLimitError(AzureDevOpsIntegrationError):
    def __init__(self, message: str = "Azure DevOps rate limit was exceeded.", *, retry_after_seconds: float = 0, **kwargs) -> None:
        super().__init__(message, code="rate_limited", retryable=True, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class AzureDevOpsTimeoutError(AzureDevOpsIntegrationError):
    def __init__(self, message: str = "Azure DevOps request timed out.", **kwargs) -> None:
        super().__init__(message, code="timeout", retryable=True, **kwargs)


class AzureDevOpsCancelledError(AzureDevOpsIntegrationError):
    def __init__(self, message: str = "Azure DevOps request was cancelled.", **kwargs) -> None:
        super().__init__(message, code="cancelled", retryable=False, **kwargs)


class AzureDevOpsNotFoundError(AzureDevOpsIntegrationError):
    def __init__(self, message: str = "Azure DevOps resource was not found.", **kwargs) -> None:
        super().__init__(message, code="not_found", retryable=False, **kwargs)


class AzureDevOpsValidationError(AzureDevOpsIntegrationError):
    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(message, code="validation_error", retryable=False, **kwargs)
