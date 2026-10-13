from __future__ import annotations

from typing import Any

from .domain_expander import expand_concepts


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "into",
    "is", "it", "its", "of", "on", "or", "so", "that", "the", "their", "this", "to", "user", "users",
    "with", "within", "through", "across", "can", "will", "need", "needs",
}


class IntentAnalyzer:
    def analyze(self, intent_model: dict[str, Any]) -> dict[str, Any]:
        business_goal = _clean(intent_model.get("businessGoal"))
        user_outcome = _clean(intent_model.get("userGoal")) or business_goal
        operational_goal = _clean(intent_model.get("operationalGoal")) or user_outcome or business_goal
        title = _clean(intent_model.get("title") or intent_model.get("workItemTitle"))
        description = _clean(intent_model.get("description") or intent_model.get("workItemDescription"))
        entities = _list(intent_model.get("entities"))
        actions = _list(intent_model.get("actions"))
        business_keywords = _list(intent_model.get("businessKeywords"))
        technical_keywords = _list(intent_model.get("technicalKeywords"))
        inferred_modules = _list(intent_model.get("inferredModules"))
        inferred_flows = _list(intent_model.get("inferredFlows"))

        business_concepts = _unique([
            *entities,
            *business_keywords,
            *[token for token in _tokenize(f"{title} {description}") if len(token) > 3],
        ])[:20]
        domain_nouns = business_concepts[:]
        business_verbs = _unique([
            *actions,
            *[token for token in _tokenize(user_outcome) if token.endswith(("e", "t", "r"))],
        ])[:12]
        operational_concepts = _unique([
            *[token for token in business_concepts if token.lower() in {"operations", "dashboard", "monitoring", "review", "alert", "alarm", "outage", "escalation"}],
            *[token for token in inferred_flows if token],
        ])[:16]
        technical_concepts = _unique([
            *technical_keywords,
            *inferred_modules,
            *[token for token in _tokenize(description) if token in {"api", "telemetry", "firmware", "authentication", "authorization", "analytics", "reporting", "audit"}],
        ])[:16]
        expanded_concepts = expand_concepts([
            *business_concepts,
            *business_verbs,
            *operational_concepts,
            *technical_concepts,
            title,
            description,
            business_goal,
            user_outcome,
            operational_goal,
        ])[:48]
        technical_verbs = _unique([
            *technical_keywords,
            *[token for token in _tokenize(description) if token in {"monitor", "review", "display", "analyze", "detect", "export", "filter", "search", "manage", "deploy", "upgrade"}],
        ])[:12]
        affected_systems = _unique([
            *_list(intent_model.get("affectedSystems")),
            *[item for item in inferred_flows if any(term in item.lower() for term in ["mobile", "backend", "api", "dashboard", "portal", "analytics", "firmware"])],
        ])[:10]
        corpus = " ".join(
            item for item in [
                title,
                description,
                business_goal,
                user_outcome,
                operational_goal,
                " ".join(domain_nouns),
                " ".join(business_verbs),
                " ".join(expanded_concepts),
                " ".join(technical_verbs),
                " ".join(inferred_modules),
                " ".join(inferred_flows),
            ] if item
        ).lower()
        return {
            "businessGoal": business_goal,
            "operationalGoal": operational_goal,
            "userOutcome": user_outcome,
            "businessConcepts": business_concepts,
            "domainNouns": domain_nouns,
            "businessVerbs": business_verbs,
            "operationalConcepts": operational_concepts,
            "technicalConcepts": technical_concepts,
            "expandedConcepts": expanded_concepts,
            "technicalVerbs": technical_verbs,
            "affectedSystems": affected_systems,
            "corpus": corpus,
            "title": title,
            "description": description,
            "inferredModules": inferred_modules,
            "inferredFlows": inferred_flows,
            "primaryCapability": _clean(intent_model.get("primaryCapability")),
            "secondaryCapabilities": _list(intent_model.get("secondaryCapabilities")),
        }


def _tokenize(value: str) -> list[str]:
    tokens = []
    for raw in value.replace("/", " ").replace("-", " ").replace("_", " ").split():
        token = raw.strip(" ,.:;()[]{}").lower()
        if token and token not in STOP_WORDS:
            tokens.append(token)
    return tokens


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
    seen: set[str] = set()
    for value in values:
        cleaned = _clean(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            output.append(cleaned)
            seen.add(key)
    return output
