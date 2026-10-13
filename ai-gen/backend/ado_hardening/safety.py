"""Non-destructive live Azure DevOps test-project safeguards."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class LiveTestSafetyError(ValueError):
    pass


def _enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _set(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


@dataclass(frozen=True)
class LiveTestSafetyPolicy:
    live_enabled: bool
    write_enabled: bool
    test_project_ids: frozenset[str]
    production_project_ids: frozenset[str]

    @classmethod
    def from_environment(cls) -> "LiveTestSafetyPolicy":
        return cls(
            live_enabled=_enabled(os.getenv("AI_GEN_ADO_LIVE_TESTS", "false")),
            write_enabled=_enabled(os.getenv("AI_GEN_ADO_TEST_WRITES", "false")),
            test_project_ids=frozenset(_set(os.getenv("AI_GEN_ADO_TEST_PROJECT_IDS", ""))),
            production_project_ids=frozenset(_set(os.getenv("AI_GEN_ADO_PRODUCTION_PROJECT_IDS", ""))),
        )

    def validate(self, request: dict[str, Any], *, executor_is_mock: bool) -> dict[str, Any]:
        mode = str(request.get("mode") or "Mocked").strip().lower()
        project_id = str(request.get("projectId") or "").strip()
        allow_writes = bool(request.get("allowWrites"))
        if mode == "mocked":
            if not executor_is_mock:
                raise LiveTestSafetyError("Mocked mode requires the dedicated mock Azure DevOps test executor.")
            return {"mode": "Mocked", "projectId": project_id or "mock-ado-project", "writesAllowed": allow_writes}
        if mode != "live":
            raise LiveTestSafetyError("mode must be Mocked or Live.")
        if not self.live_enabled:
            raise LiveTestSafetyError("Live Azure DevOps hardening is disabled. Set AI_GEN_ADO_LIVE_TESTS=true explicitly.")
        if not project_id:
            raise LiveTestSafetyError("projectId is required for live Azure DevOps hardening.")
        if project_id in self.production_project_ids:
            raise LiveTestSafetyError("The selected Azure DevOps project is registered as production and cannot be used for hardening.")
        if not self.test_project_ids or project_id not in self.test_project_ids:
            raise LiveTestSafetyError("The selected project is not in AI_GEN_ADO_TEST_PROJECT_IDS.")
        if str(request.get("projectConfirmation") or "").strip() != project_id:
            raise LiveTestSafetyError("projectConfirmation must exactly match projectId for live hardening.")
        if allow_writes and not self.write_enabled:
            raise LiveTestSafetyError("Live writes are disabled. Set AI_GEN_ADO_TEST_WRITES=true only for an isolated test project.")
        return {"mode": "Live", "projectId": project_id, "writesAllowed": allow_writes}
