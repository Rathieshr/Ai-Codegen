"""Engineering Memory policies."""

from __future__ import annotations

from typing import Any


MEMORY_CATEGORIES = [
    "Project Memory",
    "Architecture Memory",
    "Planning Memory",
    "Execution Memory",
    "QA Memory",
    "Pattern Memory",
    "Decision Memory",
    "Repository Memory",
    "Prompt Evolution",
    "Lessons Learned",
]

MEMORY_STATES = ["Draft", "Validated", "Approved", "Indexed", "Available", "Deprecated", "Archived"]

APPROVED_SOURCE_STATES = {"approved", "locked", "validated", "passed", "ready", "release ready", "ready for release"}
REJECTED_SOURCE_STATES = {"rejected", "failed", "blocked", "parse_error", "timeout"}


class MemoryPolicies:
    def normalize_category(self, value: Any) -> str:
        text = " ".join(str(value or "").replace("_", " ").split()).strip().title()
        aliases = {
            "Project": "Project Memory",
            "Architecture": "Architecture Memory",
            "Planning": "Planning Memory",
            "Execution": "Execution Memory",
            "Qa": "QA Memory",
            "Qa Memory": "QA Memory",
            "Pattern": "Pattern Memory",
            "Decision": "Decision Memory",
            "Repository": "Repository Memory",
            "Prompt": "Prompt Evolution",
            "Lesson": "Lessons Learned",
            "Lessons": "Lessons Learned",
        }
        return aliases.get(text, text if text in MEMORY_CATEGORIES else "Project Memory")

    def normalize_status(self, value: Any) -> str:
        text = " ".join(str(value or "").replace("_", " ").split()).strip().title()
        if text == "Qa":
            text = "QA"
        return text if text in MEMORY_STATES else "Draft"

    def can_learn_from_source(self, source: dict[str, Any]) -> tuple[bool, str]:
        status_values = [
            source.get("state"),
            source.get("status"),
            source.get("validationStatus"),
            source.get("validation_status"),
            source.get("approvalStatus"),
            source.get("approval_status"),
        ]
        lowered = {str(value or "").strip().lower().replace("_", " ") for value in status_values if value}
        if lowered & REJECTED_SOURCE_STATES:
            return False, "Rejected, failed, blocked, timed out, or parse-error artifacts cannot become Engineering Memory."
        if lowered & APPROVED_SOURCE_STATES:
            return True, "Source artifact is approved or validated."
        if source.get("approved_on") or source.get("validatedAt") or source.get("validated_at"):
            return True, "Source artifact has approval or validation evidence."
        return False, "Engineering Memory requires an approved or validated source artifact."

    def next_status(self, current: str) -> str:
        current = self.normalize_status(current)
        try:
            index = MEMORY_STATES.index(current)
        except ValueError:
            return "Draft"
        return MEMORY_STATES[min(index + 1, len(MEMORY_STATES) - 1)]
