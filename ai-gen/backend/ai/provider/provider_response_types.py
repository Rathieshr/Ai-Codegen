"""Types for normalized provider responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NormalizedProviderResponse:
    """Provider response converted into a content string plus provenance."""

    raw_response: Any
    content: str
    source_format: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedProviderResponse:
    """Parsed provider response after envelope normalization and JSON parsing."""

    normalized: NormalizedProviderResponse
    parsed_json: dict[str, Any]
