"""Deterministic heuristics for deciding whether to use the refiner."""

from __future__ import annotations

from backend.refinement.provider import get_refinement_provider


VARIANT_KEYWORDS = (
    "phone",
    "mobile",
    "otp",
    "filter",
    "dashboard",
    "approval",
    "role",
    "attachment",
    "document",
    "workflow",
    "validation",
    "regex",
    "limit",
    "screen",
    "page",
    "form",
)
RESPOND_KEYWORDS = ("explain", "summarize", "understand", "describe")
GENERIC_FLOWS = {"", "general", "auth", "ui"}


def should_use_refiner(
    source: str | None,
    intent: str | None,
    detected_flow: str | None,
    confidence_level: str | None,
    query: str,
    work_item: dict | None = None,
) -> tuple[bool, str]:
    """Return whether refinement would add value to this request."""

    provider = get_refinement_provider()
    if provider is None or not provider.is_enabled():
        return False, "refiner disabled"

    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return False, "query empty"
    if any(keyword in normalized_query for keyword in RESPOND_KEYWORDS) and confidence_level == "high":
        return False, "high-confidence response task"

    has_variant_signal = any(keyword in normalized_query for keyword in VARIANT_KEYWORDS)
    weak_flow = (detected_flow or "").strip().lower() in GENERIC_FLOWS
    medium_or_low_confidence = confidence_level in {"low", "medium", None, ""}
    azure_devops = (source or "").strip().lower() == "azure_devops"

    if azure_devops and medium_or_low_confidence and (weak_flow or has_variant_signal or bool(work_item)):
        return True, "azure devops task needs structured refinement"
    if medium_or_low_confidence and weak_flow and has_variant_signal and intent != "general":
        return True, "variant-heavy task needs structured refinement"

    return False, "deterministic pipeline is strong enough"
