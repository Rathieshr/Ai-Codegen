from __future__ import annotations

from typing import Any

from .capability_context import CapabilityMatch, RejectedCapability
from .capability_diagnostics import CapabilityDiagnostics
from .capability_rules import CORE_CAPABILITIES, REJECTION_RULES


def reject_irrelevant_capabilities(
    matches: list[CapabilityMatch],
    intent_model: dict[str, Any],
    diagnostics: CapabilityDiagnostics,
) -> tuple[list[CapabilityMatch], list[RejectedCapability]]:
    corpus = _intent_corpus(intent_model)
    accepted: list[CapabilityMatch] = []
    rejected: list[RejectedCapability] = []
    matched_names = {match.name for match in matches}
    for match in matches:
        rule = REJECTION_RULES.get(match.name)
        if rule and not _has_required(corpus, rule["required"]):  # type: ignore[arg-type]
            reason = str(rule["reason"])
            rejected.append(RejectedCapability(match.name, reason, 0.9))
            diagnostics.add(f"Rejected {match.name}: {reason}")
            continue
        accepted.append(match)
    for capability in CORE_CAPABILITIES:
        if capability in matched_names:
            continue
        rule = REJECTION_RULES.get(capability)
        if rule and not _has_required(corpus, rule["required"]):  # type: ignore[arg-type]
            rejected.append(RejectedCapability(capability, str(rule["reason"]), 0.72))
    return accepted, _dedupe_rejections(rejected)


def _has_required(corpus: str, required: list[str]) -> bool:
    return any(token.lower() in corpus for token in required)


def _intent_corpus(intent_model: dict[str, Any]) -> str:
    parts = [
        str(intent_model.get("businessGoal") or ""),
        str(intent_model.get("userGoal") or ""),
        str(intent_model.get("primaryCapability") or ""),
        " ".join(intent_model.get("secondaryCapabilities") or []),
        " ".join(intent_model.get("businessKeywords") or []),
        " ".join(intent_model.get("technicalKeywords") or []),
        " ".join(intent_model.get("actions") or []),
        " ".join(intent_model.get("entities") or []),
        " ".join(intent_model.get("inferredModules") or []),
        " ".join(intent_model.get("inferredFlows") or []),
    ]
    return " ".join(parts).lower()


def _dedupe_rejections(rejections: list[RejectedCapability]) -> list[RejectedCapability]:
    output: list[RejectedCapability] = []
    seen: set[str] = set()
    for rejection in rejections:
        if rejection.name not in seen:
            output.append(rejection)
            seen.add(rejection.name)
    return output

