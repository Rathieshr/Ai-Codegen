"""Shared QA Intelligence rules."""

from __future__ import annotations

from typing import Any


TEST_CATEGORIES = [
    "Functional",
    "Integration",
    "Negative",
    "Boundary",
    "Permission",
    "Security",
    "Performance",
    "Regression",
]

STATUS_COVERED = "Covered"
STATUS_PARTIAL = "Partially Covered"
STATUS_MISSING = "Missing"
STATUS_NOT_VERIFIABLE = "Not Verifiable"


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]
    if isinstance(value, dict):
        return [clean(value.get("name") or value.get("title") or value.get("path") or value.get("rule") or value.get("risk"))]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(string_list(item))
        return unique([item for item in result if item])
    text = clean(value)
    return [text] if text else []


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def text_blob(*values: Any) -> str:
    parts: list[str] = []
    for value in values:
        if isinstance(value, dict):
            parts.extend(clean(item) for item in value.values())
        elif isinstance(value, list):
            parts.extend(text_blob(item) for item in value)
        else:
            parts.append(clean(value))
    return " ".join(part for part in parts if part).lower()


def terms(value: str) -> set[str]:
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "when",
        "from",
        "this",
        "into",
        "user",
        "can",
        "are",
        "is",
        "has",
        "have",
        "must",
        "shall",
        "should",
        "able",
    }
    return {
        word.strip(".,:;()[]{}").lower()
        for word in clean(value).split()
        if len(word.strip(".,:;()[]{}")) > 3 and word.lower() not in stop_words
    }


def test_text(test: dict[str, Any]) -> str:
    return text_blob(
        test.get("title"),
        test.get("category"),
        test.get("expected_result"),
        test.get("expected"),
        test.get("preconditions"),
        test.get("steps"),
    )


def category_for(test: dict[str, Any]) -> str:
    category = clean(test.get("category"))
    lowered = category.lower()
    if "positive" in lowered or "functional" in lowered:
        return "Functional"
    if "integration" in lowered:
        return "Integration"
    if "negative" in lowered:
        return "Negative"
    if "boundary" in lowered or "edge" in lowered:
        return "Boundary"
    if "permission" in lowered or "role" in lowered or "access" in lowered:
        return "Permission"
    if "security" in lowered or "auth" in lowered:
        return "Security"
    if "performance" in lowered or "load" in lowered or "timeout" in lowered:
        return "Performance"
    if "regression" in lowered:
        return "Regression"
    return category or "Functional"


def criterion_is_verifiable(criterion: str) -> bool:
    lowered = criterion.lower()
    non_verifiable = ["improve", "better", "modern", "seamless", "intuitive", "robust", "user friendly"]
    return not any(token in lowered for token in non_verifiable) or any(char.isdigit() for char in lowered)


def test_covers_criterion(test: dict[str, Any], criterion: str) -> bool:
    text = test_text(test)
    criterion_lower = criterion.lower()
    if any(token in criterion_lower for token in ["permission", "role", "unauthorized", "access", "security"]):
        return any(token in text for token in ["permission", "role", "unauthorized", "access", "security", "authorized"])
    if any(token in criterion_lower for token in ["missing", "unavailable", "error", "timeout", "network", "retry"]):
        return any(token in text for token in ["missing", "unavailable", "error", "timeout", "network", "retry"])
    if any(token in criterion_lower for token in ["performance", "seconds", "load", "latency"]):
        return any(token in text for token in ["performance", "seconds", "timeout", "load", "latency"])
    overlap = terms(criterion_lower) & terms(text)
    return len(overlap) >= min(3, max(1, len(terms(criterion_lower))))
