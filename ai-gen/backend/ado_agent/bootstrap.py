"""Dependency registration for the Azure DevOps agent."""

from __future__ import annotations

import os
from pathlib import Path

from backend.governance.policy import PolicyEngine
from backend.platform.shared import JsonMapStore

from .policy import AzureDevOpsAgentPolicy
from .repository import AzureDevOpsAgentRepository
from .sdk_gateway import HEIPlatformSdkAdapter
from .service import AzureDevOpsAgentEventHandler, AzureDevOpsAgentJobHandler, AzureDevOpsAgentService, EVENT_TRIGGER_MAP


def register_ado_agent(
    storage_root: Path,
    *,
    platform,
    intelligence,
    automation,
    azure_devops,
    planning_pack_provider,
    policy_engine=None,
) -> AzureDevOpsAgentService:
    repository = AzureDevOpsAgentRepository(
        JsonMapStore(storage_root / "action_packs.json"),
        JsonMapStore(storage_root / "event_receipts.json"),
    )
    sdk = HEIPlatformSdkAdapter(
        intelligence=intelligence,
        automation=automation,
        azure_devops=azure_devops,
        planning_pack_provider=planning_pack_provider,
    )
    policy = AzureDevOpsAgentPolicy(
        policy_engine or PolicyEngine(),
        allow_informational_pr_comments=os.getenv("AI_GEN_ADO_AGENT_ALLOW_PR_COMMENTS", "false").lower() == "true",
    )
    service = AzureDevOpsAgentService(
        repository=repository,
        sdk=sdk,
        policy=policy,
        platform=platform,
        ttl_minutes=int(os.getenv("AI_GEN_ADO_ACTION_PACK_TTL_MINUTES", "60")),
    )
    platform.job_handlers.register("AzureDevOpsAgent", AzureDevOpsAgentJobHandler(service, platform))
    handler = AzureDevOpsAgentEventHandler(repository, platform)
    for event_type in EVENT_TRIGGER_MAP:
        platform.event_handlers.subscribe(event_type, handler)
    return service
