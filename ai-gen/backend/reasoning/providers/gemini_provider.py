"""Gemini reasoning provider adapter."""

from .base import CallableReasoningProvider, ReasoningInvoker


class GeminiProvider(CallableReasoningProvider):
    def __init__(self, model: str = "", invoker: ReasoningInvoker | None = None) -> None:
        super().__init__("Gemini", model, invoker)
