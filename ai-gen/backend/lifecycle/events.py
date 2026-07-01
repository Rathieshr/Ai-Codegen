"""Lifecycle event names and artifact constants."""

from __future__ import annotations

from typing import Any


ARTIFACT_TYPES = {
    "Epic",
    "Feature",
    "Story",
    "Task",
    "Execution Package",
    "Validation Report",
    "QA Report",
    "PR Review",
    "Release Report",
}

STAGES = ["Planning", "Execution", "Validation", "QA", "Release"]

STATE_SEQUENCE = [
    "Draft",
    "Analyzed",
    "Reviewed",
    "Approved",
    "Execution Ready",
    "Execution Package Built",
    "Execution Plan Generated",
    "Implementation Started",
    "Implementation Complete",
    "Implementation Validated",
    "QA Analysis Complete",
    "Tests Generated",
    "Coverage Verified",
    "Regression Complete",
    "Release Ready",
    "Released",
    "Archived",
]


def normalize_artifact_type(value: Any) -> str:
    text = " ".join(str(value or "").replace("_", " ").split()).strip()
    aliases = {
        "User Story": "Story",
        "Test Suite": "QA Report",
        "Coverage Report": "QA Report",
        "Implementation Validation": "Validation Report",
        "Developer Prompt": "Execution Package",
    }
    return aliases.get(text, text or "Story")


def normalize_state(value: Any) -> str:
    text = " ".join(str(value or "").replace("_", " ").split()).strip().title()
    aliases = {
        "Ready": "Release Ready",
        "Qa Ready": "Release Ready",
        "Validated": "Implementation Validated",
        "Locked": "Approved",
        "Created": "Approved",
    }
    return aliases.get(text, text if text in STATE_SEQUENCE else "Draft")
