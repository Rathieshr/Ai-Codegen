from __future__ import annotations

from typing import Any

from .capability_context import CapabilityMatch
from .capability_diagnostics import CapabilityDiagnostics
from .capability_rules import CAPABILITY_RULES, CORE_CAPABILITIES, canonical_capability, is_system_flow_name


def match_capabilities(intent_model: dict[str, Any], diagnostics: CapabilityDiagnostics) -> list[CapabilityMatch]:
    corpus = _intent_corpus(intent_model)
    intent_primary = _clean(intent_model.get("primaryCapability"))
    intent_secondary = _list(intent_model.get("secondaryCapabilities"))
    matches: list[CapabilityMatch] = []
    for capability in CORE_CAPABILITIES:
        rules = CAPABILITY_RULES.get(capability, {})
        evidence = [keyword for keyword in rules.get("keywords", []) if keyword.lower() in corpus]
        intent_boost = capability == canonical_capability(intent_primary) or capability in [canonical_capability(item) for item in intent_secondary]
        if not evidence and not intent_boost:
            continue
        confidence = 0.62 + min(len(evidence), 4) * 0.07 + (0.14 if intent_boost else 0)
        reason = f"Matched {capability} from intent keywords."
        if intent_boost:
            reason = f"Intent model identified {capability} as a capability."
        matches.append(
            CapabilityMatch(
                name=capability,
                type="capability",
                confidence=round(min(confidence, 0.96), 2),
                reason=reason,
                source="intent",
                evidence=evidence or [capability],
            )
        )
        diagnostics.add(f"Selected capability {capability}: {reason}")
    if not matches:
        matches.append(
            CapabilityMatch(
                name="Operational Awareness",
                type="capability",
                confidence=0.45,
                reason="No strong capability signal found; defaulted to operational awareness fallback.",
                source="fallback_rules",
                evidence=[],
            )
        )
        diagnostics.add("Defaulted capability selection to Operational Awareness.")
    return sorted(matches, key=lambda item: item.confidence, reverse=True)


def match_modules(
    capabilities: list[CapabilityMatch],
    intent_model: dict[str, Any],
    knowledge_registry: dict[str, Any],
    diagnostics: CapabilityDiagnostics,
) -> list[CapabilityMatch]:
    registry_modules = _list(knowledge_registry.get("modules"))
    intent_modules = _list(intent_model.get("inferredModules"))
    names = _unique([*intent_modules, *[module for capability in capabilities for module in CAPABILITY_RULES.get(canonical_capability(capability.name), {}).get("modules", [])]])
    return _match_named_context(names, registry_modules, "module", diagnostics)


def match_flows(
    capabilities: list[CapabilityMatch],
    intent_model: dict[str, Any],
    knowledge_registry: dict[str, Any],
    diagnostics: CapabilityDiagnostics,
) -> list[CapabilityMatch]:
    registry_flows = _list(knowledge_registry.get("flows"))
    intent_flows = _list(intent_model.get("inferredFlows"))
    requested = _unique([*intent_flows, *[flow for capability in capabilities for flow in CAPABILITY_RULES.get(canonical_capability(capability.name), {}).get("flows", [])]])
    invalid = [name for name in requested if is_system_flow_name(name)]
    if invalid:
        diagnostics.add(f"Rejected system/application names from flows: {', '.join(invalid)}.")
    names = [name for name in requested if not is_system_flow_name(name)]
    return _match_named_context(names, registry_flows, "flow", diagnostics)


def match_applications(
    intent_model: dict[str, Any],
    project_profile: dict[str, Any],
    diagnostics: CapabilityDiagnostics,
) -> list[CapabilityMatch]:
    apps = project_profile.get("applications") or []
    corpus = _intent_corpus(intent_model)
    flow_apps = [item for item in _list(intent_model.get("inferredFlows")) if is_system_flow_name(item)]
    primary = canonical_capability(_clean(intent_model.get("primaryCapability")))
    secondary = [canonical_capability(item) for item in _list(intent_model.get("secondaryCapabilities"))]
    capabilities = [primary, *secondary]
    matches: list[CapabilityMatch] = []
    for app in apps:
        if isinstance(app, dict):
            name = _clean(app.get("name"))
            app_type = _clean(app.get("type"))
        else:
            name = _clean(app)
            app_type = ""
        if not name:
            continue
        app_text = f"{name} {app_type}".lower()
        if "firmware" in app_text and "firmware" not in corpus:
            continue
        if "analytics" in app_text and not any(token in corpus for token in ["analytics", "trend", "metric", "kpi", "report", "reliability"]):
            continue
        if not (_application_supported_by_capability(name, app_type, capabilities, corpus) or name in flow_apps):
            continue
        confidence = 0.78 if any(token in corpus for token in [name.lower(), app_type.lower()] if token) or name in flow_apps else 0.58
        matches.append(
            CapabilityMatch(
                name=name,
                type="application",
                confidence=confidence,
                reason="Application is compatible with selected intent and not excluded by negative relevance rules.",
                source="knowledge_registry" if project_profile.get("knowledge_registry") else "fallback_rules",
                evidence=[app_type] if app_type else [],
            )
        )
    if matches:
        diagnostics.add(f"Selected {len(matches)} relevant application(s).")
    return matches[:5]


def match_dependencies(
    modules: list[CapabilityMatch],
    flows: list[CapabilityMatch],
    knowledge_registry: dict[str, Any],
    diagnostics: CapabilityDiagnostics,
) -> list[CapabilityMatch]:
    registry_deps = _list(knowledge_registry.get("dependencies"))
    names = registry_deps or [f"{item.name} owner alignment" for item in modules[:3]] + [f"{item.name} regression coverage" for item in flows[:2]]
    matches = [
        CapabilityMatch(
            name=name,
            type="dependency",
            confidence=0.58 if registry_deps else 0.46,
            reason="Dependency selected from knowledge registry." if registry_deps else "Dependency inferred from selected module or flow ownership.",
            source="knowledge_registry" if registry_deps else "fallback_rules",
            evidence=[],
        )
        for name in _unique(names)[:8]
    ]
    if matches:
        diagnostics.add(f"Selected {len(matches)} relevant dependenc(y/ies).")
    return matches


def _match_named_context(
    requested: list[str],
    registry_items: list[str],
    match_type: str,
    diagnostics: CapabilityDiagnostics,
) -> list[CapabilityMatch]:
    registry_lower = {item.lower(): item for item in registry_items}
    output: list[CapabilityMatch] = []
    for name in requested:
        source = "fallback_rules"
        confidence = 0.58
        selected_name = name
        for registry_key, registry_name in registry_lower.items():
            if name.lower() in registry_key or registry_key in name.lower():
                selected_name = registry_name
                source = "knowledge_registry"
                confidence = 0.82
                break
        output.append(
            CapabilityMatch(
                name=selected_name,
                type=match_type,  # type: ignore[arg-type]
                confidence=confidence,
                reason=f"{match_type.title()} selected from capability context.",
                source=source,  # type: ignore[arg-type]
                evidence=[name],
            )
        )
    unique = _dedupe_matches(output)
    if unique:
        diagnostics.add(f"Selected {len(unique)} relevant {match_type}(s).")
    return unique[:8]


def _intent_corpus(intent_model: dict[str, Any]) -> str:
    parts = [
        _clean(intent_model.get("businessGoal")),
        _clean(intent_model.get("userGoal")),
        _clean(intent_model.get("primaryCapability")),
        " ".join(_list(intent_model.get("secondaryCapabilities"))),
        " ".join(_list(intent_model.get("businessKeywords"))),
        " ".join(_list(intent_model.get("technicalKeywords"))),
        " ".join(_list(intent_model.get("actions"))),
        " ".join(_list(intent_model.get("entities"))),
        " ".join(_list(intent_model.get("inferredModules"))),
        " ".join(_list(intent_model.get("inferredFlows"))),
    ]
    return " ".join(part for part in parts if part).lower()


def _application_supported_by_capability(name: str, app_type: str, capabilities: list[str], corpus: str) -> bool:
    text = f"{name} {app_type}".lower()
    if "operations dashboard" in text or "web portal" in text:
        return any(capability in capabilities for capability in ["Operational Awareness", "Fault Monitoring", "Alert Management", "Outage Investigation", "Reliability Analytics"])
    if "backend" in text or "api" in text:
        return any(capability in capabilities for capability in ["Fault Monitoring", "Alert Management", "Outage Investigation", "Reliability Analytics", "Authentication", "Authorization"])
    if "mobile" in text:
        return any(token in corpus for token in ["mobile", "field technician", "field", "operator review"]) or any(capability in capabilities for capability in ["Alert Management"])
    if "analytics" in text:
        return "Reliability Analytics" in capabilities
    return any(_clean(name).lower() in corpus for _ in [0])


def _dedupe_matches(matches: list[CapabilityMatch]) -> list[CapabilityMatch]:
    output: list[CapabilityMatch] = []
    seen: set[str] = set()
    for match in matches:
        key = f"{match.type}:{match.name.lower()}"
        if key not in seen:
            output.append(match)
            seen.add(key)
    return output


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    if isinstance(value, str):
        return [_clean(item) for item in value.replace("\n", ",").split(",") if _clean(item)]
    return []


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if cleaned and cleaned not in output:
            output.append(cleaned)
    return output
