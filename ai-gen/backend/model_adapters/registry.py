"""Registry for deterministic model adapter implementations."""

from __future__ import annotations

from .claude import ClaudeModelAdapter
from .codex import CodexModelAdapter
from .gemini import GeminiModelAdapter
from .glm import GLMModelAdapter
from .gpt import GPTModelAdapter
from .ollama import OllamaModelAdapter
from .qwen import QwenModelAdapter


class ModelAdapterRegistry:
    def __init__(self) -> None:
        adapters = (
            GPTModelAdapter(),
            CodexModelAdapter(),
            ClaudeModelAdapter(),
            GeminiModelAdapter(),
            GLMModelAdapter(),
            QwenModelAdapter(),
            OllamaModelAdapter(),
        )
        self._adapters = {adapter.model_id: adapter for adapter in adapters}

    def list_ids(self) -> list[str]:
        return list(self._adapters)

    def get(self, model_id: str):
        return self._adapters.get(str(model_id or "").strip().casefold())
