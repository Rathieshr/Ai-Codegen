"""Provider-aware prompt budgeting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderCapabilities:
    """The prompt limits and features exposed by a model provider."""

    provider: str
    model: str = ""
    context_limit: int = 1200
    max_output_tokens: int = 300
    supports_json_mode: bool = False
    max_prompt_chars: int = 4800
    safety_margin: int = 180

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "context_limit": self.context_limit,
            "max_output_tokens": self.max_output_tokens,
            "supports_json_mode": self.supports_json_mode,
            "max_prompt_chars": self.max_prompt_chars,
            "safety_margin": self.safety_margin,
        }


@dataclass(slots=True)
class PromptBudgetProfile:
    """A provider-specific section budget and compression policy."""

    provider: str
    model: str = ""
    context_limit: int = 1200
    reserved_tokens: int = 180
    reserved_output_tokens: int = 250
    input_budget: int = 950
    compression_strategy: str = "aggressive"
    section_budgets: dict[str, int] = field(default_factory=dict)
    compression_order: list[str] = field(default_factory=lambda: ["draft", "knowledge", "repository"])
    removable_sources: list[str] = field(default_factory=lambda: ["examples", "diagnostics"])
    capabilities: ProviderCapabilities | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "context_limit": self.context_limit,
            "reserved_tokens": self.reserved_tokens,
            "reserved_output_tokens": self.reserved_output_tokens,
            "input_budget": self.input_budget,
            "compression_strategy": self.compression_strategy,
            "section_budgets": dict(self.section_budgets),
            "compression_order": list(self.compression_order),
            "removable_sources": list(self.removable_sources),
            "capabilities": self.capabilities.to_dict() if self.capabilities else {},
        }


@dataclass(slots=True)
class PromptSection:
    """A ranked prompt section managed before provider execution."""

    id: str
    name: str
    priority: int
    estimatedTokens: int
    required: bool
    compressible: bool
    source: str
    content: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "priority": self.priority,
            "estimatedTokens": self.estimatedTokens,
            "required": self.required,
            "compressible": self.compressible,
            "source": self.source,
            "content": self.content,
        }
