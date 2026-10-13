"""Job queue and runner foundation for platform background work."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from ..events import EventBus, PlatformEventType
from ..shared import JsonListStore, OperationStatus, now_iso, platform_result, progress_state
from .types import is_terminal, normalize_platform_job


class IJobHandler(Protocol):
    def handle(self, job: dict[str, Any]) -> dict[str, Any] | None:
        ...


class IJobQueue(Protocol):
    def enqueue(self, job: dict[str, Any]) -> dict[str, Any]:
        ...

    def dequeue(self) -> dict[str, Any] | None:
        ...

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        ...


class IJobRunner(Protocol):
    def run_next(self) -> dict[str, Any]:
        ...

    def run_job(self, job_id: str, *, dequeued_job: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class JobHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, IJobHandler] = {}

    def register(self, job_type: str, handler: IJobHandler) -> None:
        self._handlers[job_type] = handler

    def resolve(self, job_type: str) -> IJobHandler | None:
        return self._handlers.get(job_type)


class InMemoryJobQueue:
    def __init__(self, storage_path: Path) -> None:
        self._store = JsonListStore(storage_path)

    def enqueue(self, job: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_platform_job(job)
        jobs = self._store.read()
        jobs.append(normalized)
        self._store.write(jobs)
        return normalized

    def dequeue(self) -> dict[str, Any] | None:
        jobs = self._store.read()
        for index, job in enumerate(jobs):
            if job.get("status") in {OperationStatus.QUEUED.value, OperationStatus.PENDING.value}:
                selected = jobs.pop(index)
                self._store.write(jobs)
                return selected
        return None

    def list_recent(self, limit: int = 50) -> dict[str, Any]:
        jobs = self._store.read()
        recent = list(reversed(jobs[-limit:]))
        return {"jobs": recent, "count": len(jobs)}

    def get(self, job_id: str) -> dict[str, Any] | None:
        for job in self._store.read():
            if job.get("jobId") == job_id:
                return job
        return None

    def save(self, job: dict[str, Any]) -> dict[str, Any]:
        jobs = self._store.read()
        replaced = False
        for index, existing in enumerate(jobs):
            if existing.get("jobId") == job.get("jobId"):
                jobs[index] = normalize_platform_job(job)
                replaced = True
                break
        if not replaced:
            jobs.append(normalize_platform_job(job))
        self._store.write(jobs)
        return normalize_platform_job(job)

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        job = self.get(job_id)
        if not job or is_terminal(job.get("status", "")):
            return job
        job["status"] = OperationStatus.CANCELLED.value
        job["completedAt"] = job.get("completedAt") or now_iso()
        return self.save(job)

    def update_progress(self, job_id: str, progress: dict[str, Any]) -> dict[str, Any] | None:
        job = self.get(job_id)
        if not job:
            return None
        job["progress"] = progress_state(progress)
        return self.save(job)


class JobRunner:
    def __init__(
        self,
        queue: InMemoryJobQueue,
        registry: JobHandlerRegistry,
        event_bus: EventBus | None = None,
        activity_logger: Any | None = None,
    ) -> None:
        self.queue = queue
        self.registry = registry
        self.event_bus = event_bus
        self.activity_logger = activity_logger

    def run_next(self) -> dict[str, Any]:
        job = self.queue.dequeue()
        if not job:
            return platform_result(True, status=OperationStatus.SKIPPED, message="No queued jobs.")
        return self.run_job(job["jobId"], dequeued_job=job)

    def run_job(self, job_id: str, *, dequeued_job: dict[str, Any] | None = None) -> dict[str, Any]:
        job = normalize_platform_job(dequeued_job or self.queue.get(job_id) or {"jobId": job_id})
        handler = self.registry.resolve(job["jobType"])
        if not handler:
            job["status"] = OperationStatus.FAILED.value
            job["error"] = f"No job handler registered for {job['jobType']}."
            job["failedAt"] = job["failedAt"] or job["createdAt"]
            self.queue.save(job)
            return platform_result(False, status=OperationStatus.FAILED, message=job["error"], errors=[job["error"]], metadata={"job": job})
        if job["status"] == OperationStatus.CANCELLED.value:
            self.queue.save(job)
            return platform_result(False, status=OperationStatus.CANCELLED, message="Job cancelled.", metadata={"job": job})
        job["status"] = OperationStatus.RUNNING.value
        job["startedAt"] = job.get("startedAt") or job["createdAt"]
        job["progress"] = progress_state({**job.get("progress", {}), "currentStep": "Running job", "startedAt": job["startedAt"]})
        self.queue.save(job)
        try:
            result = handler.handle(job) or {}
            job["status"] = OperationStatus.COMPLETED.value
            job["completedAt"] = result.get("completedAt") or job["progress"].get("updatedAt")
            job["progress"] = progress_state(
                {
                    **job.get("progress", {}),
                    "currentStep": "Completed",
                    "completedSteps": ["Queued", "Running", "Completed"],
                    "pendingSteps": [],
                    "percentComplete": 100,
                    "startedAt": job["startedAt"],
                    "updatedAt": job["completedAt"],
                }
            )
            job["result"] = result if isinstance(result, dict) else {"value": result}
            self.queue.save(job)
            if self.activity_logger:
                self.activity_logger.add_activity(
                    {
                        "activityType": "PlatformJobCompleted",
                        "title": job["jobType"],
                        "description": f"Completed job {job['jobId']}.",
                        "source": job["source"],
                        "correlationId": job["correlationId"],
                        "metadata": {"jobId": job["jobId"]},
                    }
                )
            if self.event_bus:
                self.event_bus.publish(
                    {
                        "eventType": PlatformEventType.AGENT_RUN_COMPLETED.value,
                        "source": job["source"],
                        "correlationId": job["correlationId"],
                        "payload": {"jobId": job["jobId"], "jobType": job["jobType"]},
                    }
                )
            return platform_result(True, status=OperationStatus.COMPLETED, message="Job completed.", metadata={"job": job})
        except Exception as exc:  # pragma: no cover - explicit failure path asserted in tests
            job["retryCount"] = int(job.get("retryCount") or 0) + 1
            if job["retryCount"] <= int(job.get("maxRetries") or 0):
                job["status"] = OperationStatus.QUEUED.value
            else:
                job["status"] = OperationStatus.FAILED.value
                job["failedAt"] = job.get("failedAt") or job["progress"].get("updatedAt")
            job["error"] = str(exc)
            self.queue.save(job)
            if self.event_bus and job["status"] == OperationStatus.FAILED.value:
                self.event_bus.publish(
                    {
                        "eventType": PlatformEventType.AGENT_RUN_FAILED.value,
                        "source": job["source"],
                        "correlationId": job["correlationId"],
                        "payload": {"jobId": job["jobId"], "jobType": job["jobType"], "error": job["error"]},
                    }
                )
            return platform_result(
                False,
                status=job["status"],
                message=job["error"],
                errors=[job["error"]],
                metadata={"job": job},
            )
