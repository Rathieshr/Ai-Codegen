"""Generic platform agent runtime contracts and in-memory implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..events import EventBus, PlatformEventType
from ..shared import JsonListStore, OperationStatus, platform_result, progress_state
from .types import default_agent_context, normalize_agent_profile, normalize_agent_run


class IAgent(Protocol):
    def execute(self, context: dict[str, Any]) -> dict[str, Any] | None:
        ...


class IAgentRunner(Protocol):
    def run(
        self,
        agent: "IAgent",
        profile: dict[str, Any],
        *,
        trigger_event: dict[str, Any] | None = None,
        source: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class IAgentContextBuilder(Protocol):
    def build(self, profile: dict[str, Any], trigger_event: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
        ...


class IAgentPolicyEvaluator(Protocol):
    def evaluate(self, profile: dict[str, Any], trigger_event: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
        ...


class IAgentRunRepository(Protocol):
    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        ...

    def get(self, run_id: str) -> dict[str, Any] | None:
        ...

    def list_recent(self, limit: int = 50) -> dict[str, Any]:
        ...


class IAgentScheduler(Protocol):
    def schedule(self, profile: dict[str, Any], trigger_event: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class InMemoryAgentRunRepository:
    def __init__(self, storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)

    def save(self, run: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_agent_run(run)
        runs = self._store.read()
        replaced = False
        for index, existing in enumerate(runs):
            if existing.get("runId") == normalized["runId"]:
                runs[index] = normalized
                replaced = True
                break
        if not replaced:
            runs.append(normalized)
        self._store.write(runs)
        return normalized

    def get(self, run_id: str) -> dict[str, Any] | None:
        for run in self._store.read():
            if run.get("runId") == run_id:
                return run
        return None

    def list_recent(self, limit: int = 50) -> dict[str, Any]:
        runs = self._store.read()
        recent = list(reversed(runs[-limit:]))
        return {"runs": recent, "count": len(runs)}


class DefaultAgentContextBuilder:
    def build(self, profile: dict[str, Any], trigger_event: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
        return default_agent_context(profile, trigger_event, context)


class DefaultAgentPolicyEvaluator:
    def evaluate(self, profile: dict[str, Any], trigger_event: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_agent_profile(profile)
        if not normalized["enabled"]:
            return platform_result(False, status=OperationStatus.SKIPPED, message="Agent is disabled.")
        return platform_result(True, status=OperationStatus.RUNNING, message="Policy evaluation passed.")


class AgentRunner:
    def __init__(
        self,
        run_repository: InMemoryAgentRunRepository,
        *,
        event_bus: EventBus | None = None,
        activity_logger: Any | None = None,
        context_builder: IAgentContextBuilder | None = None,
        policy_evaluator: IAgentPolicyEvaluator | None = None,
    ) -> None:
        self._runs = run_repository
        self._event_bus = event_bus
        self._activity_logger = activity_logger
        self._context_builder = context_builder or DefaultAgentContextBuilder()
        self._policy_evaluator = policy_evaluator or DefaultAgentPolicyEvaluator()

    def run(
        self,
        agent: IAgent,
        profile: dict[str, Any],
        *,
        trigger_event: dict[str, Any] | None = None,
        source: str = "",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_profile = normalize_agent_profile(profile)
        run = normalize_agent_run(
            {
                "agentId": normalized_profile["agentId"],
                "triggerEventId": (trigger_event or {}).get("eventId", ""),
                "source": source or "Agent",
                "status": OperationStatus.PENDING.value,
                "correlationId": (trigger_event or {}).get("correlationId"),
                "input": context or {},
                "progress": {"currentStep": "Policy Evaluation", "pendingSteps": ["Context Build", "Agent Execute", "Result Published"]},
            }
        )
        self._runs.save(run)
        if self._event_bus:
            self._event_bus.publish(
                {
                    "eventType": PlatformEventType.AGENT_RUN_REQUESTED.value,
                    "source": run["source"],
                    "correlationId": run["correlationId"],
                    "payload": {"runId": run["runId"], "agentId": run["agentId"]},
                }
            )
        policy = self._policy_evaluator.evaluate(normalized_profile, trigger_event, context or {})
        if not policy.get("success"):
            run["status"] = policy.get("status", OperationStatus.SKIPPED.value)
            run["error"] = policy.get("message", "")
            self._runs.save(run)
            return run
        run["status"] = OperationStatus.RUNNING.value
        run["startedAt"] = run.get("startedAt") or run["progress"].get("updatedAt")
        run["progress"] = progress_state(
            {
                "currentStep": "Context Build",
                "completedSteps": ["Policy Evaluation"],
                "pendingSteps": ["Agent Execute", "Result Published"],
                "percentComplete": 25,
                "startedAt": run["startedAt"],
            }
        )
        self._runs.save(run)
        built_context = self._context_builder.build(normalized_profile, trigger_event, context or {})
        run["progress"] = progress_state(
            {
                "currentStep": "Agent Execute",
                "completedSteps": ["Policy Evaluation", "Context Build"],
                "pendingSteps": ["Result Published"],
                "percentComplete": 60,
                "startedAt": run["startedAt"],
            }
        )
        self._runs.save(run)
        try:
            output = agent.execute(built_context) or {}
            run["output"] = output if isinstance(output, dict) else {"value": output}
            run["status"] = OperationStatus.COMPLETED.value
            run["completedAt"] = run["progress"].get("updatedAt")
            run["progress"] = progress_state(
                {
                    "currentStep": "Completed",
                    "completedSteps": ["Policy Evaluation", "Context Build", "Agent Execute", "Result Published"],
                    "pendingSteps": [],
                    "percentComplete": 100,
                    "startedAt": run["startedAt"],
                }
            )
            self._runs.save(run)
            if self._activity_logger:
                self._activity_logger.add_activity(
                    {
                        "activityType": "AgentRunCompleted",
                        "title": normalized_profile["name"],
                        "description": f"Completed platform agent run {run['runId']}.",
                        "source": run["source"],
                        "correlationId": run["correlationId"],
                        "metadata": {"runId": run["runId"], "agentId": run["agentId"]},
                    }
                )
            if self._event_bus:
                self._event_bus.publish(
                    {
                        "eventType": PlatformEventType.AGENT_RUN_COMPLETED.value,
                        "source": run["source"],
                        "correlationId": run["correlationId"],
                        "payload": {"runId": run["runId"], "agentId": run["agentId"]},
                    }
                )
            return run
        except Exception as exc:  # pragma: no cover
            run["status"] = OperationStatus.FAILED.value
            run["failedAt"] = run["progress"].get("updatedAt")
            run["error"] = str(exc)
            self._runs.save(run)
            if self._event_bus:
                self._event_bus.publish(
                    {
                        "eventType": PlatformEventType.AGENT_RUN_FAILED.value,
                        "source": run["source"],
                        "correlationId": run["correlationId"],
                        "payload": {"runId": run["runId"], "agentId": run["agentId"], "error": run["error"]},
                    }
                )
            return run
