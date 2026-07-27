"""Guarantee complete, explainable engineering decisions."""

from __future__ import annotations

from typing import Any


class DecisionExplainer:
    def complete(
        self,
        value: dict[str, Any],
        *,
        context: dict[str, Any],
        evidence_catalog: list[dict[str, Any]],
    ) -> dict[str, Any]:
        result = dict(value)
        result["reasoning"] = _strings(result.get("reasoning")) or [
            "Recommendation is constrained to the supplied Engineering Context."
        ]
        result["alternatives"] = _alternatives(result.get("alternatives"))
        result["risks"] = _strings(result.get("risks")) or _context_risks(context)
        result["tradeOffs"] = _strings(result.get("tradeOffs")) or [
            "Additional context can improve confidence but increases prompt size."
        ]
        result["impact"] = result.get("impact") if isinstance(result.get("impact"), dict) else {}
        result["impact"].setdefault(
            "summary",
            str((context.get("impact") or {}).get("engineeringComplexity") or "Review during workflow approval."),
        )
        if not result.get("evidence") and evidence_catalog:
            result["evidence"] = [{
                "referenceId": evidence_catalog[0]["referenceId"],
                "reason": "Canonical Engineering Context used as deterministic evidence.",
            }]
        return result


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value or [] if str(item).strip()]


def _alternatives(value: Any) -> list[dict[str, Any]]:
    output = []
    for item in value or []:
        if isinstance(item, dict):
            output.append(item)
        elif str(item).strip():
            output.append({"title": str(item), "reason": "Alternative supplied by reasoning provider."})
    return output or [{
        "title": "Request human review",
        "reason": "Use when evidence coverage or confidence is insufficient.",
    }]


def _context_risks(context: dict[str, Any]) -> list[str]:
    return [
        str(item)
        for item in (context.get("impact") or {}).get("potentialRisks") or []
        if str(item).strip()
    ] or ["No explicit risk is present in Engineering Context; validate during approval."]
