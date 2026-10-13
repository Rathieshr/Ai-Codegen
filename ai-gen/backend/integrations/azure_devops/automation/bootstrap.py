"""Dependency registration for approved Azure DevOps automation."""

from __future__ import annotations

from pathlib import Path

from backend.platform.shared import JsonMapStore

from .service import AzureDevOpsAutomationService
from .store import AutomationExecutionStore


def register_ado_automation(storage_root: Path, *, azure_devops, recommendations, planning_pack_provider, platform) -> AzureDevOpsAutomationService:
    return AzureDevOpsAutomationService(
        azure_devops=azure_devops,
        recommendations=recommendations,
        execution_store=AutomationExecutionStore(JsonMapStore(storage_root / "executions.json")),
        planning_pack_provider=planning_pack_provider,
        platform=platform,
    )
