"""Reusable provider adapters for the HEI Reasoning Layer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..models import ReasoningRequest

ReasoningInvoker = Callable[[str, ReasoningRequest, str], Any]


class CallableReasoningProvider:
    """Provider implementation backed by an injected transport callable."""

    def __init__(
        self,
        name: str,
        model: str = "",
        invoker: ReasoningInvoker | None = None,
    ) -> None:
        self.name = name
        self.model = model
        self._invoker = invoker

    def is_available(self) -> bool:
        return self._invoker is not None

    def analyze(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute("analyze", prompt, request)

    def recommend(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute("recommend", prompt, request)

    def summarize(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute("summarize", prompt, request)

    def refine(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute("refine", prompt, request)

    def reason(self, prompt: str, request: ReasoningRequest) -> Any:
        return self._execute("reason", prompt, request)

    def _execute(self, operation: str, prompt: str, request: ReasoningRequest) -> Any:
        if self._invoker is None:
            raise RuntimeError(f"{self.name} reasoning provider is not configured.")
        return self._invoker(prompt, request, operation)
