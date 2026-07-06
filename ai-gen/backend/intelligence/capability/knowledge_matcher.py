from __future__ import annotations

from typing import Any

from .capability_rules import CAPABILITY_RULES, CORE_CAPABILITIES, canonical_capability


def discover_knowledge_candidates(intent_summary: dict[str, Any], knowledge_registry: dict[str, Any]) -> list[dict[str, Any]]:
    registry_modules = _list(knowledge_registry.get("modules"))
    registry_flows = _list(knowledge_registry.get("flows"))
    corpus = str(intent_summary.get("corpus") or "")
    primary = canonical_capability(str(intent_summary.get("primaryCapability") or ""))
    secondary = {canonical_capability(item) for item in _list(intent_summary.get("secondaryCapabilities"))}
    candidates: list[dict[str, Any]] = []
    for capability in CORE_CAPABILITIES:
        rules = CAPABILITY_RULES.get(capability, {})
        keywords = _list(rules.get("keywords"))
        modules = _list(rules.get("modules"))
        flows = _list(rules.get("flows"))
        keyword_hits = [keyword for keyword in keywords if keyword.lower() in corpus]
        module_hits = [module for module in modules if _contains_any(module, registry_modules, corpus)]
        flow_hits = [flow for flow in flows if _contains_any(flow, registry_flows, corpus)]
        business_hits = [token for token in intent_summary.get("domainNouns", []) if any(token.lower() in keyword.lower() or keyword.lower() in token.lower() for keyword in keywords)]
        if not any([keyword_hits, module_hits, flow_hits, business_hits, capability == primary, capability in secondary]):
            continue
        intent_score = min(100, 40 + len(keyword_hits) * 12 + (28 if capability == primary else 0) + (16 if capability in secondary else 0))
        keyword_score = min(100, 35 + len(keyword_hits) * 15 + len(business_hits) * 8)
        knowledge_score = min(100, 35 + len(module_hits) * 18 + len(flow_hits) * 18)
        business_goal_score = min(100, 30 + len(business_hits) * 18 + len(keyword_hits) * 10)
        evidence = _unique([*keyword_hits, *module_hits, *flow_hits, *business_hits])[:8]
        candidates.append(
            {
                "name": capability,
                "intent_score": intent_score,
                "keyword_score": keyword_score,
                "knowledge_score": knowledge_score,
                "business_goal_score": business_goal_score,
                "repository_score": 0,
                "memory_score": 0,
                "module_hits": module_hits[:4],
                "flow_hits": flow_hits[:4],
                "evidence": evidence,
                "knowledge_evidence": _unique([*module_hits, *flow_hits])[:6],
                "reason_seed": f"{capability} matches epic intent and knowledge registry evidence.",
            }
        )
    return candidates


def _contains_any(value: str, registry_values: list[str], corpus: str) -> bool:
    lowered = value.lower()
    if lowered in corpus:
        return True
    return any(lowered in item.lower() or item.lower() in lowered for item in registry_values)


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).strip().split())
        key = cleaned.lower()
        if cleaned and key not in seen:
            output.append(cleaned)
            seen.add(key)
    return output
