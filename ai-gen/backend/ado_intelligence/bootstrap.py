from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from backend.platform.shared import JsonMapStore
from backend.platform_sdk import as_azure_devops_sdk

from .estimation_repository import EstimationRepository
from .estimation_service import EstimationIntelligenceService
from .pr_repository import PullRequestIntelligenceRepository
from .pr_service import PullRequestIntelligenceService
from .repository import WorkItemRecommendationRepository
from .service import AdoWorkItemIntelligenceService
from .sprint_repository import SprintIntelligenceRepository
from .sprint_service import SprintIntelligenceService


def register_ado_work_item_intelligence(storage_root: Path, *, azure_devops: Any, context_orchestrator: Any, profile_provider: Callable[[], dict] | None = None, engineering_memory: Any | None = None, platform: Any | None = None) -> AdoWorkItemIntelligenceService:
    ado_sdk = as_azure_devops_sdk(azure_devops)
    repository = WorkItemRecommendationRepository(JsonMapStore(storage_root / "recommendations.json"), JsonMapStore(storage_root / "analyses.json"))
    service = AdoWorkItemIntelligenceService(azure_devops=ado_sdk, context_orchestrator=context_orchestrator, repository=repository, profile_provider=profile_provider, platform=platform)
    service.estimation = EstimationIntelligenceService(
        azure_devops=ado_sdk,
        estimates=EstimationRepository(JsonMapStore(storage_root / "estimates.json"), JsonMapStore(storage_root / "estimate_outcomes.json")),
        recommendations=repository,
        engineering_memory=engineering_memory,
        platform=platform,
    )
    platform_root = storage_root.parent
    service.pull_requests = PullRequestIntelligenceService(
        azure_devops=ado_sdk,
        repository=PullRequestIntelligenceRepository(
            JsonMapStore(storage_root / "pull_request_reports.json"),
            JsonMapStore(storage_root / "pull_request_comments.json"),
            JsonMapStore(storage_root / "pull_request_receipts.json"),
        ),
        context_stores={
            "executionPackages": JsonMapStore(platform_root / "execution_packages.json"),
            "runtimeSessions": JsonMapStore(platform_root / "execution_runtime_sessions.json"),
            "engineeringDiffs": JsonMapStore(platform_root / "engineering_diffs.json"),
            "validationResults": JsonMapStore(platform_root / "implementation_validation_reports.json"),
            "qaResults": JsonMapStore(platform_root / "qa_execution_plans.json"),
            "memoryCandidates": JsonMapStore(platform_root / "engineering_memory_candidates.json"),
            "prCandidates": JsonMapStore(platform_root / "pr_candidates.json"),
        },
        platform=platform,
    )
    if platform:
        for event_type in (
            "PullRequestCreated", "PullRequestUpdated", "PullRequestMerged",
            "AzureDevOpsPullRequestSynchronized",
        ):
            platform.event_handlers.subscribe(event_type, service.pull_requests)
    service.sprints = SprintIntelligenceService(
        azure_devops=ado_sdk,
        repository=SprintIntelligenceRepository(JsonMapStore(storage_root / "sprint_intelligence_reports.json")),
        estimation=service.estimation,
        platform=platform,
    )
    return service
