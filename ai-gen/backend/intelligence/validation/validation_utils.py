from __future__ import annotations

from typing import Any


def clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(clean(item) for item in value if clean(item))
    return " ".join(str(value).strip().split())


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [clean(item) for item in value if clean(item)]
    if isinstance(value, str):
        return [clean(item) for item in value.replace("\n", "|").split("|") if clean(item)]
    return []


def names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        name = clean(item.get("name")) if isinstance(item, dict) else clean(item)
        if name and name not in output:
            output.append(name)
    return output


def artifact_text(artifact: dict[str, Any]) -> str:
    parts = [
        clean(artifact.get("title")),
        clean(artifact.get("description")),
        clean(artifact.get("businessValue") or artifact.get("business_value")),
        clean(artifact.get("acceptanceCriteria") or artifact.get("acceptance_criteria")),
        clean(artifact.get("dependencies")),
        clean(artifact.get("risks")),
        clean(artifact.get("assumptions")),
        clean((artifact.get("generatedUsing") or {}).get("modules") if isinstance(artifact.get("generatedUsing"), dict) else ""),
        clean((artifact.get("generatedUsing") or {}).get("flows") if isinstance(artifact.get("generatedUsing"), dict) else ""),
    ]
    return " ".join(part for part in parts if part)


def context_text(planning_context: dict[str, Any]) -> str:
    parts = [
        clean(planning_context.get("businessGoal")),
        clean(planning_context.get("userProblem")),
        clean(planning_context.get("expectedOutcome")),
        clean(names(planning_context.get("selectedCapabilities"))),
        clean(names(planning_context.get("selectedModules"))),
        clean(names(planning_context.get("selectedFlows"))),
        clean(names(planning_context.get("selectedApplications"))),
        clean(names(planning_context.get("selectedStandards"))),
    ]
    return " ".join(part for part in parts if part)


def tokens(text: str) -> set[str]:
    stop = {"a", "an", "and", "are", "as", "by", "for", "from", "in", "is", "of", "on", "or", "the", "to", "with"}
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    return {token for token in normalized.split() if len(token) > 2 and token not in stop}


def similarity(left: str, right: str) -> float:
    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def score_from_overlap(left: str, right: str, base: int = 45) -> int:
    return clamp(base + int(similarity(left, right) * 65))


def clamp(value: int | float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(value))))

