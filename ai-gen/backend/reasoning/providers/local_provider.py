"""Local-model reasoning provider adapter."""

from .base import CallableReasoningProvider, ReasoningInvoker


class LocalProvider(CallableReasoningProvider):
    def __init__(self, model: str = "", invoker: ReasoningInvoker | None = None) -> None:
        super().__init__("Local", model, invoker)
