"""Provider registration and configured fallback selection."""

from __future__ import annotations

import os
from typing import Iterable

from ..interfaces import IReasoningProvider


class ReasoningProviderRegistry:
    def __init__(self, providers: Iterable[IReasoningProvider] | None = None) -> None:
        self._providers: dict[str, IReasoningProvider] = {}
        for provider in providers or ():
            self.register(provider)

    def register(self, provider: IReasoningProvider) -> None:
        self._providers[_key(provider.name)] = provider

    def get(self, name: str) -> IReasoningProvider | None:
        return self._providers.get(_key(name))

    def select(self, preference: str = "Auto") -> tuple[IReasoningProvider | None, list[str]]:
        configured = preference
        if _key(configured) in {"", "auto"}:
            configured = os.getenv("HEI_REASONING_PROVIDER", "Phi")
        fallback = [
            value.strip()
            for value in os.getenv(
                "HEI_REASONING_FALLBACK_PROVIDERS",
                "GPT,Claude,Gemini,Local,Phi",
            ).split(",")
            if value.strip()
        ]
        attempted: list[str] = []
        for name in _unique([configured, *fallback]):
            attempted.append(name)
            provider = self.get(name)
            if provider:
                try:
                    if provider.is_available():
                        return provider, attempted
                except Exception:
                    continue
        return None, attempted

    def names(self) -> list[str]:
        return [provider.name for provider in self._providers.values()]


def _key(value: str) -> str:
    aliases = {"openai": "gpt", "azure_phi": "phi", "ollama": "local"}
    key = str(value or "").strip().casefold().replace("-", "_")
    return aliases.get(key, key)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = _key(value)
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result
