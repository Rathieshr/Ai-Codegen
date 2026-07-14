"""Unified, read-only projection of HEI execution lifecycle records."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable


STAGES = (
    "Planning",
    "Execution Package",
    "Execution Plan",
    "Prompt",
    "AI Runtime",
    "Validation",
    "QA",
    "Memory",
    "Completed",
)

FAILED_STATUSES = {"failed", "timedout", "timeout", "validationfailed"}
CANCELLED_STATUSES = {"cancelled", "canceled"}
RUNTIME_COMPLETE = {"completed", "succeeded", "success"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _values(provider: Callable[[], Any]) -> list[dict[str, Any]]:
    value = provider()
    if isinstance(value, dict):
        for key in ("items", "sessions", "traces", "candidates", "plans", "decisions"):
            if isinstance(value.get(key), list):
                return [deepcopy(item) for item in value[key] if isinstance(item, dict)]
        return [deepcopy(item) for item in value.values() if isinstance(item, dict)]
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


class ExecutionCenterService:
    """Joins persisted execution artifacts without becoming a lifecycle owner."""

    def __init__(
        self,
        *,
        package_provider: Callable[[], Any],
        plan_provider: Callable[[], Any],
        prompt_provider: Callable[[], Any],
        runtime_provider: Callable[[], Any],
        trace_provider: Callable[[], Any] | None = None,
        validation_provider: Callable[[], Any] | None = None,
        qa_provider: Callable[[], Any] | None = None,
        memory_provider: Callable[[], Any] | None = None,
        pr_provider: Callable[[], Any] | None = None,
        retry_runtime: Callable[[str, str], dict[str, Any]] | None = None,
    ) -> None:
        self.package_provider = package_provider
        self.plan_provider = plan_provider
        self.prompt_provider = prompt_provider
        self.runtime_provider = runtime_provider
        self.trace_provider = trace_provider or (lambda: [])
        self.validation_provider = validation_provider or (lambda: [])
        self.qa_provider = qa_provider or (lambda: [])
        self.memory_provider = memory_provider or (lambda: [])
        self.pr_provider = pr_provider or (lambda: [])
        self.retry_runtime = retry_runtime

    def list(self, *, search: str = "", status: str = "", provider: str = "", offset: int = 0, limit: int = 100) -> dict[str, Any]:
        records = self._records()
        query = search.strip().casefold()
        if query:
            records = [item for item in records if query in " ".join((item["id"], item["title"], item["sourceArtifact"]["title"], item["provider"]["name"], item["provider"]["model"])).casefold()]
        if status:
            records = [item for item in records if item["status"].casefold() == status.casefold()]
        if provider:
            records = [item for item in records if provider.casefold() in f"{item['provider']['name']} {item['provider']['model']}".casefold()]
        safe_offset = max(0, offset)
        safe_limit = min(250, max(1, limit))
        page = records[safe_offset:safe_offset + safe_limit]
        return {
            "schemaVersion": "hei-execution-center-v1",
            "summary": self._summary(records),
            "items": page,
            "filters": {
                "statuses": sorted({item["status"] for item in records}),
                "providers": sorted({item["provider"]["name"] for item in records if item["provider"]["name"]}),
            },
            "pagination": {"total": len(records), "offset": safe_offset, "limit": safe_limit, "returned": len(page), "hasMore": safe_offset + len(page) < len(records)},
            "generatedAt": _now(),
        }

    def get(self, execution_id: str) -> dict[str, Any]:
        record = next((item for item in self._records() if execution_id in {item["id"], item["package"]["id"], item["runtime"]["sessionId"]}), None)
        if not record:
            raise LookupError(f"Execution {execution_id} was not found.")
        return record

    def timeline(self, execution_id: str) -> dict[str, Any]:
        record = self.get(execution_id)
        return {"executionId": record["id"], "status": record["status"], "currentStage": record["currentStage"], "timeline": record["timeline"], "correlationId": record["correlationId"]}

    def diagnostics(self, execution_id: str) -> dict[str, Any]:
        record = self.get(execution_id)
        return {
            "executionId": record["id"],
            "correlationId": record["correlationId"],
            "lineage": record["lineage"],
            "package": record["package"].get("diagnostics", {}),
            "plan": record["plan"].get("diagnostics", {}),
            "prompt": record["prompt"].get("diagnostics", {}),
            "runtime": record["runtime"].get("diagnostics", {}),
            "validation": record["validation"],
            "qa": record["qa"],
            "memory": record["memory"],
            "prCandidate": record["prCandidate"],
            "warnings": record["warnings"],
            "traceabilityComplete": all(record["lineage"].get(key) for key in ("packageId", "planId", "promptId", "sessionId")),
        }

    def retry(self, execution_id: str, reason: str = "") -> dict[str, Any]:
        if not self.retry_runtime:
            raise ValueError("Execution retry is not available.")
        record = self.get(execution_id)
        session_id = record["runtime"]["sessionId"]
        if not session_id:
            raise ValueError("Execution has no AI Runtime session to retry.")
        return self.retry_runtime(session_id, reason or "Retried from Execution Center.")

    def _records(self) -> list[dict[str, Any]]:
        packages = _values(self.package_provider)
        plans = _values(self.plan_provider)
        prompts = _values(self.prompt_provider)
        runtimes = _values(self.runtime_provider)
        traces = _values(self.trace_provider)
        validations = _values(self.validation_provider)
        qa_plans = _values(self.qa_provider)
        memories = _values(self.memory_provider)
        prs = _values(self.pr_provider)
        records: list[dict[str, Any]] = []
        matched_sessions: set[str] = set()
        for package in packages:
            package_id = _text(package.get("packageId") or _dict(package.get("metadata")).get("packageId"))
            plan = next((item for item in plans if _text(item.get("sourcePackageId")) == package_id), {})
            prompt = next((item for item in prompts if _text(item.get("executionManifestId")) == _text(plan.get("manifestId")) or _text(item.get("sourcePackageId")) == package_id), {})
            runtime = self._runtime_for(package, plan, prompt, runtimes)
            if runtime.get("sessionId"):
                matched_sessions.add(_text(runtime["sessionId"]))
            records.append(self._project(package, plan, prompt, runtime, traces, validations, qa_plans, memories, prs))
        for runtime in runtimes:
            if _text(runtime.get("sessionId")) not in matched_sessions:
                records.append(self._project({}, {}, {}, runtime, traces, validations, qa_plans, memories, prs))
        records.sort(key=lambda item: item["updatedAt"], reverse=True)
        return records

    def _runtime_for(self, package: dict[str, Any], plan: dict[str, Any], prompt: dict[str, Any], runtimes: list[dict[str, Any]]) -> dict[str, Any]:
        package_id = _text(package.get("packageId"))
        plan_id = _text(plan.get("manifestId"))
        prompt_id = _text(prompt.get("compiledPromptId"))
        versions = {_text(_dict(package.get("metadata")).get("packageVersion")), package_id, plan_id, _text(plan.get("manifestVersion")), prompt_id}
        versions.discard("")
        for runtime in runtimes:
            context = _dict(runtime.get("runtimeContext"))
            runtime_values = {
                _text(runtime.get("executionPackageVersion")), _text(runtime.get("executionPlanVersion")),
                _text(runtime.get("executionPromptId")), _text(context.get("packageId")), _text(context.get("manifestId")),
            }
            if versions & runtime_values:
                return runtime
        return {}

    def _project(self, package: dict[str, Any], plan: dict[str, Any], prompt: dict[str, Any], runtime: dict[str, Any], traces: list[dict[str, Any]], validations: list[dict[str, Any]], qa_plans: list[dict[str, Any]], memories: list[dict[str, Any]], prs: list[dict[str, Any]]) -> dict[str, Any]:
        package_id = _text(package.get("packageId") or _dict(package.get("metadata")).get("packageId"))
        session_id = _text(runtime.get("sessionId"))
        correlation_id = _text(runtime.get("correlationId") or _dict(package.get("diagnostics")).get("correlationId"))
        trace = next((item for item in traces if _text(item.get("sessionId")) == session_id or correlation_id and _text(item.get("correlationId")) == correlation_id), {})
        validation = self._related(validations, package_id, session_id, correlation_id)
        qa = self._related(qa_plans, package_id, session_id, correlation_id)
        related_memory = [item for item in memories if self._matches(item, package_id, session_id, correlation_id)]
        pr = next((item for item in prs if self._matches(item, package_id, session_id, correlation_id)), {})
        timeline = self._timeline(package, plan, prompt, runtime, validation, qa, related_memory, trace)
        current = next((item["stage"] for item in timeline if item["status"] in {"Failed", "Cancelled"}), "")
        current = current or next((item["stage"] for item in timeline if item["status"] == "Active"), "Completed" if timeline[-1]["status"] == "Completed" else "Planning")
        source = _dict(package.get("planningContext"))
        story = _dict(source.get("story"))
        task = _dict(source.get("task"))
        title = _text(task.get("title") or story.get("title") or _dict(package.get("businessContext")).get("storyTitle") or session_id or package_id or "Execution")
        runtime_status = _text(runtime.get("status"))
        overall = self._overall_status(timeline, runtime_status)
        updated = max((_text(value) for value in (runtime.get("completedAt"), runtime.get("startedAt"), prompt.get("compiledAt"), plan.get("generatedAt"), package.get("generatedAt"), _dict(package.get("metadata")).get("generatedAt")) if value), default="")
        return {
            "id": package_id or session_id,
            "title": title,
            "sourceArtifact": {"id": _text(task.get("id") or story.get("id") or package.get("taskId") or package.get("storyId")), "type": "Task" if task or package.get("taskId") else "Story", "title": title},
            "status": overall,
            "currentStage": current,
            "executionStatus": runtime_status or overall,
            "package": self._artifact(package_id, _text(_dict(package.get("metadata")).get("status") or _dict(package.get("readiness")).get("status")), package.get("generatedAt") or _dict(package.get("metadata")).get("generatedAt"), package),
            "plan": self._artifact(_text(plan.get("manifestId")), "Ready" if plan else "Not Started", plan.get("generatedAt"), plan),
            "prompt": self._artifact(_text(prompt.get("compiledPromptId")), "Ready" if prompt else "Not Started", prompt.get("compiledAt"), prompt),
            "provider": {"name": _text(runtime.get("provider")) or "Not selected", "model": _text(runtime.get("model")) or "Not selected"},
            "runtime": {"sessionId": session_id, "status": runtime_status or "Not Started", "startedAt": _text(runtime.get("startedAt")), "completedAt": _text(runtime.get("completedAt")), "duration": runtime.get("duration", 0), "recoverable": bool(_dict(runtime.get("diagnostics")).get("recoverable") or runtime.get("recoverable") or runtime_status.casefold() in FAILED_STATUSES | CANCELLED_STATUSES), "attempt": int(runtime.get("attempt") or 0), "diagnostics": _dict(runtime.get("diagnostics"))},
            "validation": self._stage_artifact(validation, "decisionId", "Not Started"),
            "qa": self._stage_artifact(qa, "planId", "Not Started"),
            "memory": {"status": self._memory_status(related_memory), "count": len(related_memory), "candidates": related_memory},
            "prCandidate": self._stage_artifact(pr, "candidateId", "Not Generated"),
            "timeline": timeline,
            "lineage": {"packageId": package_id, "planId": _text(plan.get("manifestId")), "promptId": _text(prompt.get("compiledPromptId")), "sessionId": session_id, "correlationId": correlation_id, "repositorySnapshotVersion": _text(runtime.get("repositorySnapshotVersion") or _dict(package.get("metadata")).get("repositorySnapshotVersion"))},
            "correlationId": correlation_id,
            "warnings": list(dict.fromkeys([*_list(_dict(package.get("diagnostics")).get("warnings")), *_list(runtime.get("warnings")), *_list(_dict(trace.get("metrics")).get("warnings"))])),
            "updatedAt": updated,
        }

    def _timeline(self, package: dict, plan: dict, prompt: dict, runtime: dict, validation: dict, qa: dict, memories: list[dict], trace: dict) -> list[dict[str, Any]]:
        runtime_status = _text(runtime.get("status")).casefold()
        exists = [True, bool(package), bool(plan), bool(prompt), bool(runtime), bool(validation), bool(qa), bool(memories)]
        timestamps = [
            _text(_dict(package.get("planningContext")).get("approvedAt") or package.get("generatedAt")),
            _text(package.get("generatedAt") or _dict(package.get("metadata")).get("generatedAt")),
            _text(plan.get("generatedAt")), _text(prompt.get("compiledAt")), _text(runtime.get("startedAt")),
            _text(validation.get("decidedAt") or validation.get("generatedAt")), _text(qa.get("generatedAt")),
            max((_text(item.get("createdAt")) for item in memories), default=""), _text(runtime.get("completedAt") or trace.get("completedAt")),
        ]
        failure_index = 4 if runtime_status in FAILED_STATUSES | CANCELLED_STATUSES else -1
        complete = runtime_status in RUNTIME_COMPLETE and bool(validation) and bool(qa) and bool(memories)
        result = []
        for index, stage in enumerate(STAGES):
            if index == 8:
                status = "Completed" if complete else "Not Started"
            elif index == failure_index:
                status = "Cancelled" if runtime_status in CANCELLED_STATUSES else "Failed"
            elif exists[index]:
                if index == 4 and runtime_status not in RUNTIME_COMPLETE:
                    status = "Active"
                else:
                    status = "Completed"
            elif any(exists[index + 1:]):
                status = "Missing"
            elif all(exists[:index]):
                status = "Active"
            else:
                status = "Not Started"
            result.append({"stage": stage, "status": status, "at": timestamps[index], "detail": self._stage_detail(stage, package, plan, prompt, runtime, validation, qa, memories)})
        return result

    @staticmethod
    def _stage_detail(stage: str, package: dict, plan: dict, prompt: dict, runtime: dict, validation: dict, qa: dict, memories: list[dict]) -> str:
        return {
            "Planning": "Approved source artifact" if package else "Waiting for approved Story or Task",
            "Execution Package": _text(package.get("packageId")) or "Package not built",
            "Execution Plan": _text(plan.get("manifestId")) or "Plan not generated",
            "Prompt": _text(prompt.get("compiledPromptId")) or "Prompt not compiled",
            "AI Runtime": _text(runtime.get("status")) or "Runtime not started",
            "Validation": _text(validation.get("decision") or validation.get("status")) or "Validation not run",
            "QA": _text(qa.get("decision") or qa.get("status")) or "QA not run",
            "Memory": f"{len(memories)} candidate(s)" if memories else "No memory candidate",
            "Completed": "Execution lifecycle complete" if memories else "Downstream work remains",
        }[stage]

    @staticmethod
    def _artifact(identifier: str, status: str, generated_at: Any, value: dict) -> dict[str, Any]:
        return {"id": identifier, "status": status or ("Ready" if identifier else "Not Started"), "generatedAt": _text(generated_at), "version": _text(value.get("manifestVersion") or _dict(value.get("metadata")).get("packageVersion") or value.get("compilerVersion")), "diagnostics": _dict(value.get("diagnostics"))}

    @staticmethod
    def _stage_artifact(value: dict, id_key: str, empty: str) -> dict[str, Any]:
        return {"id": _text(value.get(id_key)), "status": _text(value.get("status") or value.get("decision") or value.get("approvalStatus")) or ("Ready" if value else empty), "summary": _text(value.get("reason") or value.get("summary")), "data": value}

    @staticmethod
    def _memory_status(values: list[dict]) -> str:
        if not values:
            return "Not Generated"
        if any(_text(item.get("approvalStatus")).casefold() == "approved" for item in values):
            return "Approved"
        return "Pending Approval"

    @staticmethod
    def _overall_status(timeline: list[dict], runtime_status: str) -> str:
        if any(item["status"] == "Failed" for item in timeline):
            return "Failed"
        if any(item["status"] == "Cancelled" for item in timeline):
            return "Cancelled"
        if timeline[-1]["status"] == "Completed":
            return "Completed"
        if runtime_status:
            return "In Progress"
        return "Ready"

    @staticmethod
    def _matches(item: dict, package_id: str, session_id: str, correlation_id: str) -> bool:
        lineage = _dict(item.get("sourceLineage"))
        values = {_text(item.get("packageId")), _text(item.get("sessionId")), _text(item.get("correlationId")), _text(lineage.get("packageId")), _text(lineage.get("sessionId")), _text(lineage.get("correlationId"))}
        return bool(({package_id, session_id, correlation_id} - {""}) & values)

    def _related(self, values: list[dict], package_id: str, session_id: str, correlation_id: str) -> dict[str, Any]:
        return next((item for item in values if self._matches(item, package_id, session_id, correlation_id)), {})

    @staticmethod
    def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "total": len(records),
            "inProgress": sum(1 for item in records if item["status"] == "In Progress"),
            "completed": sum(1 for item in records if item["status"] == "Completed"),
            "failed": sum(1 for item in records if item["status"] == "Failed"),
            "cancelled": sum(1 for item in records if item["status"] == "Cancelled"),
            "pendingValidation": sum(1 for item in records if item["validation"]["status"] == "Not Started"),
            "pendingQA": sum(1 for item in records if item["qa"]["status"] == "Not Started"),
            "memoryCandidates": sum(item["memory"]["count"] for item in records),
        }
