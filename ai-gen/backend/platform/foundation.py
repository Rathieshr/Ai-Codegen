"""Shared platform foundation for HEI v2 services."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .activity import ActivityLogService
from .agents import AgentRunner, InMemoryAgentRunRepository
from .audit import AuditService
from .events import EventBus, EventHandlerRegistry
from .health import PlatformHealthService
from .jobs import InMemoryJobQueue, JobHandlerRegistry, JobRunner
from .notifications import NotificationService


class PlatformFoundation:
    def __init__(self, storage_root: Path | None = None) -> None:
        data_dir = Path(os.getenv("AI_GEN_DATA_DIR", str(Path(__file__).parent.parent.parent / "data")))
        self._root = storage_root or data_dir / "platform"
        self._root.mkdir(parents=True, exist_ok=True)

        self.activity = ActivityLogService(self._root / "activity.json")
        self.audit = AuditService(self._root / "audit.json")
        self.event_handlers = EventHandlerRegistry()
        self.events = EventBus(self._root / "events.json", self.event_handlers, self.activity)

        self.job_handlers = JobHandlerRegistry()
        self.jobs = InMemoryJobQueue(self._root / "jobs.json")
        self.job_runner = JobRunner(self.jobs, self.job_handlers, self.events, self.activity)

        self.agent_runs = InMemoryAgentRunRepository(self._root / "agent_runs.json")
        self.agent_runner = AgentRunner(self.agent_runs, event_bus=self.events, activity_logger=self.activity)

        self.notifications = NotificationService(self._root / "notifications.json", self.events)
        self.health = PlatformHealthService(self)

    @property
    def storage_root(self) -> Path:
        return self._root

    def platform_health(self) -> dict[str, Any]:
        return self.health.status()
