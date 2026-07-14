"""Architecture checks for the Azure DevOps operational boundary."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


REQUIRED_STAGES = (
    "IntegrationAdapter", "PlatformJobEvent", "HEIPlatformSDK",
    "IntelligenceService", "ApprovalPack", "ApprovedAutomationCommand",
    "AzureDevOps", "AuditActivity",
)


class AzureDevOpsArchitectureVerifier:
    def __init__(self, backend_root: Path) -> None:
        self.backend_root = backend_root

    def verify(self, sdk: Any, observed_stages: list[str]) -> dict[str, Any]:
        violations = self._direct_access_violations()
        stages = list(dict.fromkeys(observed_stages))
        missing = [stage for stage in REQUIRED_STAGES if stage not in stages]
        sdk_ok = sdk.__class__.__module__.startswith("backend.platform_sdk")
        checks = [
            _check("intelligence_uses_sdk", not violations, "Intelligence modules contain no direct Azure DevOps transport or integration access.", violations),
            _check("sdk_boundary", sdk_ok, "Operational validation is executed through the HEI Platform SDK."),
            _check("architecture_trace", not missing, "The correlation trace covers the complete approved ADO lifecycle.", missing),
        ]
        return {"passed": all(item["passed"] for item in checks), "checks": checks, "observedStages": stages, "missingStages": missing, "violations": violations}

    def _direct_access_violations(self) -> list[str]:
        root = self.backend_root / "ado_intelligence"
        violations: list[str] = []
        for path in sorted(root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                    if any(name.startswith("backend.integrations.azure_devops") and not name.endswith(".domain") for name in modules):
                        violations.append(f"{path.name}:{node.lineno}:direct integration import")
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self" and node.attr == "azure_devops":
                    violations.append(f"{path.name}:{node.lineno}:self.azure_devops")
        return sorted(set(violations))


def _check(check_id: str, passed: bool, details: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {"checkId": check_id, "passed": bool(passed), "status": "Passed" if passed else "Failed", "details": details, "evidence": evidence or []}
