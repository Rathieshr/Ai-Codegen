"""Dependency registration for the Azure DevOps integration foundation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from backend.platform.shared import JsonMapStore

from .application import (
    AzureDevOpsConnectionService, AzureDevOpsIterationService, AzureDevOpsProjectService,
    AzureDevOpsPullRequestService, AzureDevOpsRepositoryService, AzureDevOpsWebhookService,
    AzureDevOpsReconciliationScheduler, AzureDevOpsWorkItemService, AzureDevOpsSyncJobHandler, AzureDevOpsSyncService,
    AzureDevOpsWebhookSyncJobHandler,
)
from .infrastructure import (
    AzureDevOpsCacheStore, AzureDevOpsClientFactory, AzureDevOpsConnectionRepository,
    AzureDevOpsMappingStore, AzureDevOpsSyncRepository, AzureDevOpsWebhookReceiptStore,
    EnvironmentAzureDevOpsCredentialProvider,
)


@dataclass
class AzureDevOpsIntegrationModule:
    connections: AzureDevOpsConnectionService
    projects: AzureDevOpsProjectService
    work_items: AzureDevOpsWorkItemService
    repositories: AzureDevOpsRepositoryService
    pull_requests: AzureDevOpsPullRequestService
    iterations: AzureDevOpsIterationService
    webhooks: AzureDevOpsWebhookService
    sync: AzureDevOpsSyncService
    reconciliation_scheduler: AzureDevOpsReconciliationScheduler


def register_azure_devops_integration(storage_root: Path, *, platform=None, credential_provider=None, client_factory=None) -> AzureDevOpsIntegrationModule:
    repository = AzureDevOpsConnectionRepository(JsonMapStore(storage_root / "connections.json"))
    factory = client_factory or AzureDevOpsClientFactory(credential_provider or EnvironmentAzureDevOpsCredentialProvider())
    connections = AzureDevOpsConnectionService(repository, factory, platform=platform)
    projects = AzureDevOpsProjectService(connections, platform=platform)
    work_items = AzureDevOpsWorkItemService(connections, platform=platform)
    repositories = AzureDevOpsRepositoryService(connections, platform=platform)
    pull_requests = AzureDevOpsPullRequestService(connections, platform=platform)
    iterations = AzureDevOpsIterationService(connections, platform=platform)
    sync = AzureDevOpsSyncService(
        connections=connections, projects=projects, work_items=work_items,
        repositories=repositories, pull_requests=pull_requests, iterations=iterations,
        syncs=AzureDevOpsSyncRepository(JsonMapStore(storage_root / "syncs.json")),
        cache=AzureDevOpsCacheStore(JsonMapStore(storage_root / "cache.json")),
        mappings=AzureDevOpsMappingStore(JsonMapStore(storage_root / "mappings.json")),
        receipts=AzureDevOpsWebhookReceiptStore(JsonMapStore(storage_root / "webhook_receipts.json")),
        platform=platform,
        reconciliation_hours=int(os.getenv("AI_GEN_ADO_RECONCILIATION_HOURS", "24")),
    )
    if platform:
        platform.job_handlers.register("AzureDevOpsSync", AzureDevOpsSyncJobHandler(sync))
        platform.job_handlers.register("AzureDevOpsWebhookSync", AzureDevOpsWebhookSyncJobHandler(sync))
    return AzureDevOpsIntegrationModule(
        connections=connections,
        projects=projects,
        work_items=work_items,
        repositories=repositories,
        pull_requests=pull_requests,
        iterations=iterations,
        webhooks=AzureDevOpsWebhookService(connections, platform=platform),
        sync=sync,
        reconciliation_scheduler=AzureDevOpsReconciliationScheduler(sync),
    )
