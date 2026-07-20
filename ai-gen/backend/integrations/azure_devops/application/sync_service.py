"""Centralized Azure DevOps synchronization and reconciliation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from ..domain import (
    AzureDevOpsMapping, AzureDevOpsSync, AzureDevOpsSyncStatus, AzureDevOpsSyncType,
    AzureDevOpsValidationError, now_iso,
)


CORE_COLLECTIONS = {"projects", "workItems", "repositories"}


def _id(value: dict[str, Any], *names: str) -> str:
    return str(next((value.get(name) for name in names if value.get(name) not in (None, "")), ""))


def _records(values: list[dict[str, Any]], *names: str) -> dict[str, dict[str, Any]]:
    return {key: value for value in values if (key := _id(value, *names))}


class AzureDevOpsSyncService:
    def __init__(
        self,
        *,
        connections,
        projects,
        work_items,
        repositories,
        pull_requests,
        iterations,
        syncs,
        cache,
        mappings,
        receipts,
        platform=None,
        reconciliation_hours: int = 24,
    ) -> None:
        self.connections = connections
        self.projects = projects
        self.work_items = work_items
        self.repositories = repositories
        self.pull_requests = pull_requests
        self.iterations = iterations
        self.syncs = syncs
        self.cache = cache
        self.mappings = mappings
        self.receipts = receipts
        self.platform = platform
        self.reconciliation_hours = max(1, reconciliation_hours)

    def request_sync(
        self,
        connection_id: str,
        project_id: str,
        sync_type: str = AzureDevOpsSyncType.MANUAL.value,
        *,
        correlation_id: str = "",
    ) -> dict[str, Any]:
        self.connections.require(connection_id)
        if sync_type not in {item.value for item in AzureDevOpsSyncType}:
            raise AzureDevOpsValidationError(f"Unsupported Azure DevOps sync type: {sync_type}.", correlation_id=correlation_id)
        correlation_id = correlation_id or f"corr-{uuid4().hex[:16]}"
        sync = AzureDevOpsSync(
            sync_id=f"ado-sync-{uuid4().hex[:12]}", connection_id=connection_id,
            project_id=project_id, sync_type=sync_type, correlation_id=correlation_id,
        )
        self.syncs.save(sync)
        self._publish("AzureDevOpsSyncRequested", sync)
        job = self._enqueue("AzureDevOpsSync", {
            "syncId": sync.sync_id, "connectionId": connection_id,
            "projectId": project_id, "syncType": sync_type,
        }, correlation_id)
        return {"sync": sync.to_dict(), "job": job}

    def run_sync(self, sync_id: str) -> dict[str, Any]:
        sync = self.syncs.get(sync_id)
        if not sync:
            raise ValueError(f"Azure DevOps sync '{sync_id}' was not found.")
        sync.status = AzureDevOpsSyncStatus.RUNNING.value
        sync.started_at = sync.started_at or now_iso()
        sync.error = ""
        self.syncs.save(sync)
        self._publish("AzureDevOpsSyncStarted", sync)
        previous = self._previous_success(sync)
        try:
            mode = sync.sync_type
            if mode in {AzureDevOpsSyncType.INITIAL_FULL.value, AzureDevOpsSyncType.MANUAL.value}:
                self._full(sync)
            elif mode == AzureDevOpsSyncType.SCHEDULED_RECONCILIATION.value:
                self._reconcile(sync, previous)
            else:
                self._incremental(sync, previous)
            sync.status = AzureDevOpsSyncStatus.PARTIAL.value if sync.warnings else AzureDevOpsSyncStatus.COMPLETED.value
            sync.completed_at = now_iso()
            sync.cursor = self._next_cursor(sync, previous)
            self.syncs.save(sync)
            self._publish("AzureDevOpsSyncCompleted", sync)
            return sync.to_dict()
        except Exception as error:
            sync.status = AzureDevOpsSyncStatus.FAILED.value
            sync.error = str(error)
            sync.completed_at = now_iso()
            self.syncs.save(sync)
            self._publish("AzureDevOpsSyncFailed", sync, {"error": sync.error})
            raise

    def status(self, project_id: str) -> dict[str, Any]:
        latest = self.syncs.latest(project_id)
        cache = self.cache.snapshot(project_id)
        collections = {name: len(value) for name, value in cache.items() if isinstance(value, dict) and name != "updatedAt"}
        next_reconciliation = ""
        if latest and latest.completed_at:
            try:
                next_reconciliation = (datetime.fromisoformat(latest.completed_at) + timedelta(hours=self.reconciliation_hours)).isoformat()
            except ValueError:
                pass
        return {
            "projectId": project_id,
            "latestSync": latest.to_dict() if latest else None,
            "collectionCounts": collections,
            "centralized": True,
            "sourceOfTruth": "Azure DevOps",
            "reconciliationIntervalHours": self.reconciliation_hours,
            "nextReconciliationAt": next_reconciliation,
        }

    def history(self, project_id: str, limit: int = 50) -> dict[str, Any]:
        values = self.syncs.history(project_id, limit)
        return {"projectId": project_id, "syncs": values, "count": len(values)}

    def request_reconciliation(self, connection_id: str, project_id: str, *, correlation_id: str = "") -> dict[str, Any]:
        return self.request_sync(connection_id, project_id, AzureDevOpsSyncType.SCHEDULED_RECONCILIATION.value, correlation_id=correlation_id)

    def run_queued_job(self, job_id: str) -> dict[str, Any]:
        """Run an enqueued ADO job, including its configured transient retries."""
        runner = getattr(self.platform, "job_runner", None) if self.platform else None
        if not runner or not job_id:
            return {"success": False, "status": "NotStarted", "message": "Platform job runner is unavailable."}
        result: dict[str, Any] = {}
        for _ in range(3):
            result = runner.run_job(job_id)
            if str(result.get("status") or "") != "Queued":
                break
        return result

    def enqueue_due_reconciliations(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        queued: list[dict[str, Any]] = []
        for mapping in self.mappings.list():
            if mapping.get("mappingType") != "project":
                continue
            project_id = str(mapping.get("externalId") or "")
            active = any(
                item.get("status") in {AzureDevOpsSyncStatus.QUEUED.value, AzureDevOpsSyncStatus.RUNNING.value}
                for item in self.syncs.history(project_id, 200)
            )
            if active:
                continue
            latest = self.syncs.latest(project_id, successful_only=True)
            due = not latest or not latest.completed_at
            if latest and latest.completed_at:
                try:
                    due = datetime.fromisoformat(latest.completed_at) + timedelta(hours=self.reconciliation_hours) <= now
                except ValueError:
                    due = True
            if due:
                queued.append(self.request_reconciliation(str(mapping.get("connectionId") or ""), project_id))
        return queued

    def receive_webhook(self, payload: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
        resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else {}
        project = resource.get("project") if isinstance(resource.get("project"), dict) else {}
        containers = payload.get("resourceContainers") if isinstance(payload.get("resourceContainers"), dict) else {}
        project_container = containers.get("project") if isinstance(containers.get("project"), dict) else {}
        connection_id = str(payload.get("connectionId") or payload.get("connection_id") or "")
        project_id = str(payload.get("projectId") or payload.get("project_id") or project.get("id") or project_container.get("id") or "")
        if project_id and not connection_id:
            mapping = next((item for item in self.mappings.list(project_id) if item.get("mappingType") == "project" and item.get("externalId") == project_id), None)
            connection_id = str((mapping or {}).get("connectionId") or "")
        if not connection_id or not project_id:
            raise AzureDevOpsValidationError("connectionId and projectId are required for Azure DevOps webhooks.", correlation_id=correlation_id)
        self.connections.require(connection_id)
        event_id, accepted = self.receipts.reserve(payload)
        if not accepted:
            receipt = self.receipts.get(event_id) or {}
            return {"accepted": True, "duplicate": True, "eventId": event_id, "syncId": receipt.get("syncId"), "correlationId": correlation_id}
        correlation_id = correlation_id or f"corr-{uuid4().hex[:16]}"
        sync = AzureDevOpsSync(
            sync_id=f"ado-sync-{uuid4().hex[:12]}", connection_id=connection_id,
            project_id=project_id, sync_type=AzureDevOpsSyncType.WEBHOOK.value,
            correlation_id=correlation_id,
        )
        self.syncs.save(sync)
        self.receipts.link(event_id, sync.sync_id)
        self._publish("AzureDevOpsSyncRequested", sync, {"eventId": event_id})
        job = self._enqueue("AzureDevOpsWebhookSync", {
            "eventId": event_id, "syncId": sync.sync_id, "connectionId": connection_id,
            "projectId": project_id, "payload": payload,
        }, correlation_id)
        return {"accepted": True, "duplicate": False, "eventId": event_id, "sync": sync.to_dict(), "job": job}

    def run_webhook(self, event_id: str, sync_id: str, connection_id: str, project_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        event_type = str(payload.get("eventType") or payload.get("event_type") or "").lower()
        resource = payload.get("resource") if isinstance(payload.get("resource"), dict) else {}
        sync = self.syncs.get(sync_id)
        if not sync:
            raise ValueError(f"Azure DevOps webhook sync '{sync_id}' was not found.")
        sync.status = AzureDevOpsSyncStatus.RUNNING.value
        sync.started_at = sync.started_at or now_iso()
        sync.error = ""
        self.syncs.save(sync)
        self._publish("AzureDevOpsSyncStarted", sync, {"eventId": event_id})
        try:
            if event_type == "workitem.deleted":
                work_item_id = _id(resource, "id", "workItemId")
                deleted = sum(self.cache.delete(project_id, name, work_item_id) for name in ("workItems", "workItemHierarchy", "workItemRevisions"))
                sync.items_read = 1
                sync.items_deleted = deleted
                result = {"eventId": event_id, "eventType": event_type, "itemsDeleted": deleted}
            elif event_type.startswith("workitem."):
                work_item_id = int(_id(resource, "id", "workItemId") or 0)
                item = self.work_items.get_hierarchy(connection_id, project_id, work_item_id, correlation_id=correlation_id)
                outcome = self.cache.upsert(project_id, "workItems", str(work_item_id), item, revision_field="revision")
                self.cache.upsert(project_id, "workItemHierarchy", str(work_item_id), {"workItemId": work_item_id, "links": item.get("links") or [], "revision": item.get("revision")}, revision_field="revision")
                revisions = self.work_items.get_revisions(connection_id, project_id, work_item_id, correlation_id=correlation_id)
                self.cache.upsert(project_id, "workItemRevisions", str(work_item_id), {"workItemId": work_item_id, "revisions": revisions, "revision": item.get("revision")}, revision_field="revision")
                self._publish_named("AzureDevOpsWorkItemSynchronized", project_id, correlation_id, {"workItemId": work_item_id, "result": outcome})
                sync.items_read = 1
                sync.items_created = int(outcome == "created")
                sync.items_updated = int(outcome == "updated")
                result = {"eventId": event_id, "eventType": event_type, "result": outcome}
            elif event_type.startswith("git.pullrequest."):
                repository = resource.get("repository") if isinstance(resource.get("repository"), dict) else {}
                repository_id = str(repository.get("id") or payload.get("repositoryId") or "")
                pull_request_id = int(resource.get("pullRequestId") or resource.get("id") or 0)
                item = self.pull_requests.get_pull_request_context(connection_id, project_id, repository_id, pull_request_id, correlation_id=correlation_id)
                outcome = self.cache.upsert(project_id, "pullRequests", str(pull_request_id), item)
                self._publish_named("AzureDevOpsPullRequestSynchronized", project_id, correlation_id, {"pullRequestId": pull_request_id, "result": outcome})
                sync.items_read = 1
                sync.items_created = int(outcome == "created")
                sync.items_updated = int(outcome == "updated")
                result = {"eventId": event_id, "eventType": event_type, "result": outcome}
            elif event_type == "build.complete":
                build_id = _id(resource, "id", "buildId")
                builds = self.pull_requests.list_builds(connection_id, project_id, correlation_id=correlation_id)
                item = next((value for value in builds if _id(value, "buildId") == build_id), resource)
                outcome = self.cache.upsert(project_id, "builds", build_id, item)
                self._publish_named("AzureDevOpsBuildSynchronized", project_id, correlation_id, {"buildId": build_id, "result": outcome})
                sync.items_read = 1
                sync.items_created = int(outcome == "created")
                sync.items_updated = int(outcome == "updated")
                result = {"eventId": event_id, "eventType": event_type, "result": outcome}
            elif event_type == "git.push":
                result = self.request_sync(connection_id, project_id, AzureDevOpsSyncType.INCREMENTAL.value, correlation_id=correlation_id)
            else:
                result = {"eventId": event_id, "eventType": event_type, "ignored": True}
                sync.warnings.append(f"Unsupported Azure DevOps webhook event type: {event_type or 'Unknown'}.")
            sync.status = AzureDevOpsSyncStatus.PARTIAL.value if sync.warnings else AzureDevOpsSyncStatus.COMPLETED.value
            sync.completed_at = now_iso()
            sync.cursor = self._next_cursor(sync, self._previous_success(sync))
            self.syncs.save(sync)
            self.receipts.complete(event_id)
            self._publish("AzureDevOpsSyncCompleted", sync, {"eventId": event_id})
            return result
        except Exception as error:
            sync.status = AzureDevOpsSyncStatus.FAILED.value
            sync.error = str(error)
            sync.completed_at = now_iso()
            self.syncs.save(sync)
            self.receipts.complete(event_id, "Failed")
            self._publish("AzureDevOpsSyncFailed", sync, {"eventId": event_id, "error": sync.error})
            raise

    def save_mapping(self, mapping_type: str, hei_id: str, external_id: str, connection_id: str, project_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.mappings.save(AzureDevOpsMapping(
            mapping_id=f"{mapping_type}:{hei_id}", mapping_type=mapping_type,
            hei_id=hei_id, external_id=external_id, connection_id=connection_id,
            project_id=project_id, metadata=metadata or {},
        ))

    def _full(self, sync: AzureDevOpsSync) -> None:
        project = self.projects.get_project(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id)
        self._replace(sync, "projects", _records([project], "projectId"))
        self.save_mapping("project", sync.project_id, sync.project_id, sync.connection_id, sync.project_id, {"name": project.get("name")})
        self._safe(sync, "teams", lambda: self._replace(sync, "teams", _records(self.projects.list_teams(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id), "teamId")))
        self._safe(sync, "iterations", lambda: self._replace(sync, "iterations", _records(self.iterations.list_iterations(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id), "iterationId")))
        items = self.work_items.query(sync.connection_id, sync.project_id, self._wiql(sync.project_id), correlation_id=sync.correlation_id)
        self._replace(sync, "workItems", _records(items, "workItemId"))
        self._sync_work_item_details(sync, items, replace=True)
        repositories = self.repositories.list_repositories(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id)
        self._replace(sync, "repositories", _records(repositories, "repositoryId"))
        for repository in repositories:
            repository_id = _id(repository, "repositoryId")
            self.save_mapping("repository", repository_id, repository_id, sync.connection_id, sync.project_id, {"name": repository.get("name")})
        self._safe(sync, "pullRequests", lambda: self._replace(sync, "pullRequests", _records(self.pull_requests.list_pull_requests(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id), "pullRequestId")))
        self._safe(sync, "builds", lambda: self._replace(sync, "builds", _records(self.pull_requests.list_builds(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id), "buildId")))

    def _incremental(self, sync: AzureDevOpsSync, previous: AzureDevOpsSync | None) -> None:
        cursor = previous.cursor if previous else ""
        if not cursor:
            self._full(sync)
            return
        items = self.work_items.query(sync.connection_id, sync.project_id, self._wiql(sync.project_id, cursor), correlation_id=sync.correlation_id)
        for item in items:
            self._upsert(sync, "workItems", _id(item, "workItemId"), item, revision_field="revision")
        self._sync_work_item_details(sync, items, replace=False)
        self._safe(sync, "repositories", lambda: self._upsert_many(sync, "repositories", self.repositories.list_repositories(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id), "repositoryId"))
        self._safe(sync, "pullRequests", lambda: self._upsert_many(sync, "pullRequests", self.pull_requests.list_pull_requests(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id), "pullRequestId"))
        self._safe(sync, "builds", lambda: self._upsert_many(sync, "builds", self.pull_requests.list_builds(sync.connection_id, sync.project_id, correlation_id=sync.correlation_id), "buildId"))

    def _reconcile(self, sync: AzureDevOpsSync, previous: AzureDevOpsSync | None) -> None:
        snapshot = self.cache.snapshot(sync.project_id)
        missing = {name for name in CORE_COLLECTIONS if not snapshot.get(name)}
        if not previous or missing:
            self._publish("AzureDevOpsReconciliationRequired", sync, {"missingCollections": sorted(missing)})
            self._full(sync)
        else:
            self._incremental(sync, previous)

    def _sync_work_item_details(self, sync: AzureDevOpsSync, items: list[dict[str, Any]], *, replace: bool) -> None:
        hierarchy: dict[str, dict[str, Any]] = {}
        revisions: dict[str, dict[str, Any]] = {}
        for item in items:
            key = _id(item, "workItemId")
            enriched = item
            try:
                enriched = self.work_items.get_details(sync.connection_id, sync.project_id, int(key), correlation_id=sync.correlation_id)
                self.cache.upsert(sync.project_id, "workItems", key, enriched, revision_field="revision")
            except Exception as error:
                sync.warnings.append(f"workItemDetails:{key}: {error}")
            hierarchy[key] = {"workItemId": enriched.get("workItemId"), "links": enriched.get("links") or [], "revision": enriched.get("revision")}
            self.save_mapping("artifact", key, key, sync.connection_id, sync.project_id, {"workItemType": item.get("workItemType")})
            self._publish("AzureDevOpsWorkItemSynchronized", sync, {"workItemId": item.get("workItemId")})
            try:
                values = self.work_items.get_revisions(sync.connection_id, sync.project_id, int(key), correlation_id=sync.correlation_id)
                revisions[key] = {"workItemId": item.get("workItemId"), "revisions": values, "revision": item.get("revision")}
            except Exception as error:
                sync.warnings.append(f"workItemRevisions:{key}: {error}")
        if replace:
            self._replace(sync, "workItemHierarchy", hierarchy)
            self._replace(sync, "workItemRevisions", revisions)
        else:
            self._upsert_many(sync, "workItemHierarchy", list(hierarchy.values()), "workItemId", revision_field="revision")
            self._upsert_many(sync, "workItemRevisions", list(revisions.values()), "workItemId", revision_field="revision")

    def _replace(self, sync: AzureDevOpsSync, name: str, records: dict[str, dict[str, Any]]) -> None:
        created, updated, deleted = self.cache.replace(sync.project_id, name, records)
        sync.items_read += len(records)
        sync.items_created += created
        sync.items_updated += updated
        sync.items_deleted += deleted
        if name == "pullRequests":
            for key in records:
                self._publish("AzureDevOpsPullRequestSynchronized", sync, {"pullRequestId": key})
        if name == "builds":
            for key in records:
                self._publish("AzureDevOpsBuildSynchronized", sync, {"buildId": key})

    def _upsert(self, sync: AzureDevOpsSync, name: str, key: str, value: dict[str, Any], *, revision_field: str = "") -> str:
        sync.items_read += 1
        result = self.cache.upsert(sync.project_id, name, key, value, revision_field=revision_field)
        sync.items_created += result == "created"
        sync.items_updated += result == "updated"
        return result

    def _upsert_many(self, sync: AzureDevOpsSync, name: str, values: list[dict[str, Any]], key_name: str, *, revision_field: str = "") -> None:
        for value in values:
            key = _id(value, key_name)
            if key:
                self._upsert(sync, name, key, value, revision_field=revision_field)

    def _safe(self, sync: AzureDevOpsSync, section: str, action: Callable[[], Any]) -> None:
        try:
            action()
        except Exception as error:
            sync.warnings.append(f"{section}: {error}")

    def _previous_success(self, sync: AzureDevOpsSync) -> AzureDevOpsSync | None:
        return next((AzureDevOpsSync.from_dict(value) for value in self.syncs.history(sync.project_id, 200) if value.get("syncId") != sync.sync_id and value.get("status") in {"Completed", "Partial"}), None)

    def _next_cursor(self, sync: AzureDevOpsSync, previous: AzureDevOpsSync | None) -> str:
        values = self.cache.collection(sync.project_id, "workItems").values()
        changed = sorted(str(value.get("changedAt") or "") for value in values if value.get("changedAt"))
        return changed[-1] if changed else (previous.cursor if previous else sync.completed_at)

    def _wiql(self, project_id: str, cursor: str = "") -> str:
        where = "[System.TeamProject] = @project"
        if cursor:
            safe_cursor = cursor.replace("'", "''")
            where += f" AND [System.ChangedDate] > '{safe_cursor}'"
        return f"SELECT [System.Id] FROM WorkItems WHERE {where} ORDER BY [System.ChangedDate] ASC"

    def _enqueue(self, job_type: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
        if not self.platform:
            return {"jobType": job_type, "status": "NotQueued", "reason": "Platform job framework is unavailable."}
        return self.platform.jobs.enqueue({"jobType": job_type, "source": "AzureDevOps", "correlationId": correlation_id, "maxRetries": 2, "payload": payload})

    def _publish(self, event_type: str, sync: AzureDevOpsSync, extra: dict[str, Any] | None = None) -> None:
        self._publish_named(event_type, sync.project_id, sync.correlation_id, {"syncId": sync.sync_id, "connectionId": sync.connection_id, "syncType": sync.sync_type, **(extra or {})})

    def _publish_named(self, event_type: str, project_id: str, correlation_id: str, payload: dict[str, Any]) -> None:
        if self.platform:
            self.platform.events.publish({"eventType": event_type, "source": "AzureDevOps", "projectId": project_id, "correlationId": correlation_id, "payload": payload})


class AzureDevOpsSyncJobHandler:
    def __init__(self, service: AzureDevOpsSyncService) -> None:
        self.service = service

    def handle(self, job: dict[str, Any]) -> dict[str, Any]:
        return self.service.run_sync(str(job.get("payload", {}).get("syncId") or ""))


class AzureDevOpsWebhookSyncJobHandler:
    def __init__(self, service: AzureDevOpsSyncService) -> None:
        self.service = service

    def handle(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = job.get("payload", {})
        return self.service.run_webhook(
            str(payload.get("eventId") or ""), str(payload.get("syncId") or ""),
            str(payload.get("connectionId") or ""),
            str(payload.get("projectId") or ""), dict(payload.get("payload") or {}),
            str(job.get("correlationId") or ""),
        )


class AzureDevOpsReconciliationScheduler:
    """Scheduler entry point; the platform host invokes `run_due` periodically."""

    def __init__(self, service: AzureDevOpsSyncService) -> None:
        self.service = service

    def run_due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        return self.service.enqueue_due_reconciliations(now=now)
