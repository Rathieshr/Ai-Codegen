"""OpenAI reasoning provider adapter."""

from .base import CallableReasoningProvider, ReasoningInvoker


class OpenAIProvider(CallableReasoningProvider):
    def __init__(self, model: str = "", invoker: ReasoningInvoker | None = None) -> None:
        super().__init__("GPT", model, invoker)
