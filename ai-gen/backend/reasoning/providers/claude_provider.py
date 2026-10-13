"""Claude reasoning provider adapter."""

from .base import CallableReasoningProvider, ReasoningInvoker


class ClaudeProvider(CallableReasoningProvider):
    def __init__(self, model: str = "", invoker: ReasoningInvoker | None = None) -> None:
        super().__init__("Claude", model, invoker)
