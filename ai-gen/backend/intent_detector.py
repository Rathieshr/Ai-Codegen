"""Deterministic intent detection for user queries."""

from __future__ import annotations

import re


def detect_intent(query: str) -> str:
    """Return the broad intent for a developer request."""

    tokens = set(re.findall(r"[a-z0-9]+", query.lower()))

    if tokens.intersection({"fix", "bug", "error"}):
        return "bug_fix"
    if tokens.intersection({"add", "create", "build"}):
        return "feature"
    if tokens.intersection({"refactor", "optimize", "improve"}):
        return "refactor"
    return "general"
