from __future__ import annotations

from .intent_diagnostics import IntentDiagnostics
from .intent_rules import (
    ACTION_RULES,
    CAPABILITY_RULES,
    DOMAIN_RULES,
    ENTITY_RULES,
    FLOW_HINTS,
    MODULE_HINTS,
    PERSONA_RULES,
    TECHNICAL_KEYWORDS,
)


def _contains(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def match_rule_groups(text: str, rules: dict[str, list[str]], diagnostics: IntentDiagnostics, kind: str) -> list[str]:
    matches: list[str] = []
    lowered = text.lower()
    for label, needles in rules.items():
        evidence = next((needle for needle in needles if needle.lower() in lowered), "")
        if evidence:
            matches.append(label)
            diagnostics.matched(f"{kind} {label}", evidence)
    return matches


def _rank_rule_groups(text: str, rules: dict[str, list[str]], diagnostics: IntentDiagnostics, kind: str) -> list[str]:
    lowered = text.lower()
    scored: list[tuple[int, int, str, str]] = []
    for order, (label, needles) in enumerate(rules.items()):
        matched = [needle for needle in needles if needle.lower() in lowered]
        if matched:
            phrase_bonus = sum(1 for needle in matched if " " in needle)
            scored.append((len(matched) + phrase_bonus, -order, label, matched[0]))
    scored.sort(reverse=True)
    labels: list[str] = []
    for _, _, label, evidence in scored:
        labels.append(label)
        diagnostics.matched(f"{kind} {label}", evidence)
    return labels


def detect_capabilities(text: str, diagnostics: IntentDiagnostics) -> tuple[str, list[str]]:
    matches = _rank_rule_groups(text, CAPABILITY_RULES, diagnostics, "capability")
    if not matches:
        diagnostics.add("No explicit capability keyword found; defaulted to Operational Awareness.")
        return "Operational Awareness", []
    return matches[0], matches[1:]


def detect_domain(text: str, diagnostics: IntentDiagnostics) -> str:
    matches = _rank_rule_groups(text, DOMAIN_RULES, diagnostics, "domain")
    if matches:
        return matches[0]
    diagnostics.add("No explicit domain keyword found; defaulted to Operations.")
    return "Operations"


def detect_personas(text: str, diagnostics: IntentDiagnostics) -> list[str]:
    personas = match_rule_groups(text, PERSONA_RULES, diagnostics, "persona")
    if not personas and any(_contains(text, token) for token in ["outage", "fault", "alert", "dashboard", "operation"]):
        personas = ["Operations User"]
        diagnostics.add("Inferred Operations User from operations language.")
    return personas


def detect_actions(text: str, diagnostics: IntentDiagnostics) -> list[str]:
    return match_rule_groups(text, ACTION_RULES, diagnostics, "action")


def detect_entities(text: str, diagnostics: IntentDiagnostics) -> list[str]:
    return match_rule_groups(text, ENTITY_RULES, diagnostics, "entity")


def detect_technical_keywords(text: str, diagnostics: IntentDiagnostics) -> list[str]:
    found = [keyword for keyword in TECHNICAL_KEYWORDS if _contains(text, keyword)]
    for keyword in found:
        diagnostics.matched("technical keyword", keyword)
    return found


def infer_modules(text: str, diagnostics: IntentDiagnostics) -> list[str]:
    return match_rule_groups(text, MODULE_HINTS, diagnostics, "module hint")


def infer_flows(text: str, diagnostics: IntentDiagnostics) -> list[str]:
    return match_rule_groups(text, FLOW_HINTS, diagnostics, "flow hint")
