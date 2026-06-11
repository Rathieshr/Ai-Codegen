"""Azure DevOps automation package for ai-gen backend."""

from .client import AdoClient, AdoConfig, AdoClientError
from .automation import AdoAutomation, AutomationResult

__all__ = [
    "AdoClient",
    "AdoConfig",
    "AdoClientError",
    "AdoAutomation",
    "AutomationResult",
]
