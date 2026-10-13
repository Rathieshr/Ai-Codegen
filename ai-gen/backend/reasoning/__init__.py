"""HEI provider-neutral, deterministic-first Reasoning AI Layer."""

from .interfaces import IReasoningProvider
from .models import (
    BuiltReasoningPrompt,
    EvidenceReference,
    ReasoningRequest,
    ReasoningResult,
    ReasoningTelemetry,
)
from .providers import (
    CallableReasoningProvider,
    ClaudeProvider,
    GeminiProvider,
    LocalProvider,
    OpenAIProvider,
    PhiProvider,
    ReasoningProviderRegistry,
)
from .services import ReasoningEngine

_default_engine: ReasoningEngine | None = None


def get_reasoning_engine() -> ReasoningEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = ReasoningEngine()
    return _default_engine


def reason(workflow_type: str, engineering_context: object, **kwargs: object) -> dict:
    return get_reasoning_engine().reason(workflow_type, engineering_context, **kwargs)


def analyze(workflow_type: str, engineering_context: object, **kwargs: object) -> dict:
    return get_reasoning_engine().analyze(workflow_type, engineering_context, **kwargs)


def recommend(workflow_type: str, engineering_context: object, **kwargs: object) -> dict:
    return get_reasoning_engine().recommend(workflow_type, engineering_context, **kwargs)


def refine(workflow_type: str, engineering_context: object, **kwargs: object) -> dict:
    return get_reasoning_engine().refine(workflow_type, engineering_context, **kwargs)


def summarize(workflow_type: str, engineering_context: object, **kwargs: object) -> dict:
    return get_reasoning_engine().summarize(workflow_type, engineering_context, **kwargs)


def explain(workflow_type: str, engineering_context: object, **kwargs: object) -> dict:
    return get_reasoning_engine().explain(workflow_type, engineering_context, **kwargs)


__all__ = [
    "BuiltReasoningPrompt",
    "CallableReasoningProvider",
    "ClaudeProvider",
    "EvidenceReference",
    "GeminiProvider",
    "IReasoningProvider",
    "LocalProvider",
    "OpenAIProvider",
    "PhiProvider",
    "ReasoningEngine",
    "ReasoningProviderRegistry",
    "ReasoningRequest",
    "ReasoningResult",
    "ReasoningTelemetry",
    "analyze",
    "explain",
    "get_reasoning_engine",
    "reason",
    "recommend",
    "refine",
    "summarize",
]
