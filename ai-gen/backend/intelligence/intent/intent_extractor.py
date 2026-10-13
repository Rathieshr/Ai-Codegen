from __future__ import annotations

import re
from typing import Any

from .intent_diagnostics import IntentDiagnostics
from .intent_rules import STOP_WORDS


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(clean_text(item) for item in value)
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_type(value: Any) -> str:
    text = clean_text(value).lower().replace("_", " ")
    if text in {"epic"}:
        return "Epic"
    if text in {"feature"}:
        return "Feature"
    if text in {"story", "user story", "userstory"}:
        return "Story"
    if text in {"task"}:
        return "Task"
    return "Story"


def work_item_text(work_item: dict[str, Any]) -> str:
    parts = [
        clean_text(work_item.get("title")),
        clean_text(work_item.get("description")),
        clean_text(work_item.get("acceptance_criteria") or work_item.get("acceptanceCriteria")),
        clean_text(work_item.get("business_value") or work_item.get("businessValue")),
        clean_text(work_item.get("tags")),
        clean_text(work_item.get("area_path") or work_item.get("areaPath")),
    ]
    parent = work_item.get("parent") or work_item.get("parent_work_item") or work_item.get("parentWorkItem")
    if isinstance(parent, dict):
        parts.extend([clean_text(parent.get("title")), clean_text(parent.get("description"))])
    return " ".join(part for part in parts if part)


def extract_user_story_goal(text: str, diagnostics: IntentDiagnostics) -> tuple[str, list[str]]:
    pattern = re.compile(r"as an? (?P<persona>[^,]+),?\s+i want (?P<goal>.+?)(?:\s+so that\s+(?P<value>.+?))?(?:\.|$)", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return "", []
    persona = clean_text(match.group("persona")).title()
    goal = re.sub(r"^(to\s+)+", "", clean_text(match.group("goal")), flags=re.IGNORECASE)
    value = clean_text(match.group("value"))
    diagnostics.add("Extracted explicit user-story goal.")
    user_goal = f"{persona} wants to {goal}"
    if value:
        user_goal = f"{user_goal} so that {value}"
    return user_goal, [persona]


def extract_keywords(text: str, limit: int = 18) -> list[str]:
    phrases = re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[- ][A-Za-z0-9]+){0,2}", text)
    keywords: list[str] = []
    for phrase in phrases:
        normalized = clean_text(phrase).strip(".,:;()[]{}")
        if not normalized:
            continue
        words = [word for word in re.split(r"[\s-]+", normalized) if word]
        if len(words) == 1 and words[0].lower() in STOP_WORDS:
            continue
        if len(words) == 1 and len(words[0]) < 4:
            continue
        candidate = " ".join(word.capitalize() if word.islower() else word for word in words)
        if candidate not in keywords:
            keywords.append(candidate)
        if len(keywords) >= limit:
            break
    return keywords
