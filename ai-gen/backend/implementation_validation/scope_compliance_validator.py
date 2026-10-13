"""Scope compliance checks for implementation changes."""

from __future__ import annotations

from typing import Any

from .models import clean, string_list, violation


class ScopeComplianceValidator:
    def validate(self, execution_package: dict[str, Any], changed_files: list[dict[str, Any]]) -> dict[str, Any]:
        boundary = execution_package.get("implementationBoundary") if isinstance(execution_package.get("implementationBoundary"), dict) else {}
        blocked = string_list(boundary.get("blockedModules")) + string_list(boundary.get("outOfScope"))
        in_scope = string_list(boundary.get("inScope")) + string_list(boundary.get("allowedModules")) + string_list(boundary.get("allowedFlows"))
        violations = []
        touched_blocked: list[str] = []
        for file in changed_files:
            path = clean(file.get("path"))
            haystack = path.casefold()
            for item in blocked:
                if _matches(item, haystack):
                    touched_blocked.append(item)
                    violations.append(
                        violation(
                            rule="blocked_scope_modified",
                            severity="critical",
                            message=f"Changed file touches blocked or out-of-scope area: {item}.",
                            file_path=path,
                            recommendation="Remove this change or update the approved Execution Package scope before proceeding.",
                        )
                    )
        if not changed_files:
            score = 50
        elif violations:
            score = max(0, 100 - 35 * len(violations))
        elif in_scope:
            matched = sum(1 for file in changed_files if any(_matches(item, clean(file.get("path")).casefold()) for item in in_scope))
            score = 100 if matched else 75
        else:
            score = 85
        return {"score": score, "violations": violations, "touchedBlockedScope": touched_blocked}


def _matches(scope_item: str, haystack: str) -> bool:
    compact = clean(scope_item).casefold()
    if not compact:
        return False
    tokens = [token for token in compact.replace("/", " ").replace("-", " ").split() if len(token) >= 4]
    return compact in haystack or any(token in haystack for token in tokens)
