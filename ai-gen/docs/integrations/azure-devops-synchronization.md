# Azure DevOps Synchronization

## Purpose

Azure DevOps remains the system of record. HEI maintains one centralized, normalized cache per mapped project so Planning, Execution, QA, and portal clients do not independently fetch and index the same engineering records.

Repository source code is deliberately excluded. Repository Intelligence owns code synchronization, parsing, snapshots, graphs, and file ranking.

```text
Azure DevOps service hooks / reconciliation schedule / manual request
  -> Platform Job Framework
  -> Azure DevOps Synchronization Service
  -> normalized centralized cache and stable mappings
  -> HEI intelligence consumers
```

## Synchronization Types

- `InitialFullSync`: establishes projects, teams, iterations, work items, hierarchy, revisions, repositories, pull requests, and builds.
- `IncrementalSync`: queries work items changed after the last successful cursor and upserts mutable repository, PR, and build metadata.
- `WebhookSync`: applies one idempotent service-hook event.
- `ScheduledReconciliation`: runs incremental consistency repair and performs a full synchronization only when the cursor or a core collection is missing.
- `ManualSync`: uses the existing cursor when available and falls back to an initial synchronization for a new project.

Every run persists its status, cursor, item counters, warnings, error, and correlation ID. Partial section failures retain successfully synchronized data and are reported as `Partial`; core failures are retried by the Platform Job Framework.

## Change Tracking

The successful sync cursor is based on Azure DevOps `System.ChangedDate`. Incremental WIQL includes only work items newer than that cursor. Work-item webhook updates are revision-aware, so older out-of-order events cannot overwrite a newer cached revision.

Full synchronization replaces complete normalized collections and records created, updated, and deleted counts. It does not retrieve repository file contents.

## Event Processing

The global webhook route accepts:

- `workitem.created`, `workitem.updated`, `workitem.deleted`
- `git.pullrequest.created`, `git.pullrequest.updated`, `git.pullrequest.merged`
- `build.complete`
- `git.push`

Webhook receipts are keyed by the Azure DevOps notification ID, or by a deterministic payload hash when no ID is supplied. A duplicate delivery returns the existing receipt and does not queue another job. Push events queue an incremental synchronization.

## Reconciliation

`AI_GEN_ADO_RECONCILIATION_HOURS` configures the interval and defaults to `24`. The scheduler calls `enqueue_due_reconciliations`; the service does not run a daily full synchronization. A full repair occurs only when no successful cursor exists or a core projects, work-items, or repositories collection is missing.

## Stable Mappings

The mapping store supports stable links for:

- HEI project to ADO project
- HEI artifact to ADO work item
- HEI repository to ADO repository
- HEI execution package to ADO story or task
- HEI runtime session to branch or pull request

Initial synchronization creates project, artifact, and repository mappings. Execution and runtime services can add their mapping types through the same store without calling Azure DevOps directly.

## API

- `POST /integrations/azure-devops/projects/{projectId}/sync`
- `GET /integrations/azure-devops/projects/{projectId}/sync-status`
- `GET /integrations/azure-devops/projects/{projectId}/sync-history`
- `POST /integrations/azure-devops/webhooks`
- `POST /integrations/azure-devops/projects/{projectId}/reconcile`

Synchronization and reconciliation requests return queued jobs. The Platform SDK exposes the same operations as `syncProject`, `getSyncStatus`, `getSyncHistory`, `receiveWebhook`, and `reconcileProject`.

## Events And Diagnostics

- `AzureDevOpsSyncRequested`
- `AzureDevOpsSyncStarted`
- `AzureDevOpsSyncCompleted`
- `AzureDevOpsSyncFailed`
- `AzureDevOpsWorkItemSynchronized`
- `AzureDevOpsPullRequestSynchronized`
- `AzureDevOpsBuildSynchronized`
- `AzureDevOpsReconciliationRequired`

All jobs and events preserve the request correlation ID. Sync status includes collection counts, latest cursor, warnings, source-of-truth declaration, and next reconciliation time.

## Ownership And Safety

ADO owns canonical fields, state, assignment, iteration, hierarchy, PR status, and build status. HEI stores only normalized cached representations, mappings, sync versions, and diagnostics. This module has no work-item, repository, PR, or build write operation.
