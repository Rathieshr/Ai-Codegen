# Azure DevOps Operational Validation

## Phase 6.10 Gate

Phase 6.10 is the final gate before Command Center UI work. It validates the deployed HEI services against one isolated Azure DevOps test project. Mocked runs verify contracts only and always leave UI readiness `Blocked`.

## Required Architecture

```text
ADO event
  -> integration adapter
  -> platform job/event
  -> HEI Platform SDK
  -> intelligence service
  -> approval pack
  -> approved automation command
  -> Azure DevOps
  -> audit and activity
```

Work-item, estimation, PR, and sprint intelligence receive `HEIAzureDevOpsSdk`. They do not import Azure DevOps clients or access integration stores directly. The operational runner uses `HEIPhase6Sdk`; transport details remain behind that contract.

## Operational Flows

One run executes nine flows under one correlation ID:

1. Planning Pack approval and Epic/Feature/Story/Task creation.
2. Existing work-item analysis, recommendation approval, and update.
3. Story estimate/dependency recommendation and approved application.
4. PR analysis grounded in an Execution Package and actual changed files, followed by an approved comment.
5. Stale recommendation detection after a work-item revision change.
6. Duplicate service-hook delivery processed once.
7. Removed write permission producing a safe, audited failure.
8. Scheduled reconciliation repairing a missed service hook.
9. Sprint reporting from synchronized ADO work items.

## Safety Configuration

Live execution is off by default. Configure only a disposable or dedicated test project:

```text
AI_GEN_ADO_LIVE_TESTS=true
AI_GEN_ADO_TEST_WRITES=true
AI_GEN_ADO_TEST_PROJECT_IDS=<test-project-id>
AI_GEN_ADO_PRODUCTION_PROJECT_IDS=<production-project-ids>
```

Never include a production project in `AI_GEN_ADO_TEST_PROJECT_IDS`. The request must repeat the test project ID in `projectConfirmation`.

## Live Request

Call `POST /ado-operational-validation/run` with current test fixtures:

```json
{
  "mode": "Live",
  "projectId": "<test-project-id>",
  "projectConfirmation": "<test-project-id>",
  "connectionId": "<connection-id>",
  "repositoryId": "<repository-id>",
  "planningPackId": "<approved-planning-pack-id>",
  "workItemId": "<existing-work-item-id>",
  "storyWorkItemId": "<story-id>",
  "pullRequestId": "<pull-request-id>",
  "iterationId": "<iteration-id>",
  "staleRecommendationId": "<stale-recommendation-id>",
  "permissionRecommendationId": "<permission-test-recommendation-id>",
  "allowWrites": true,
  "approver": "<test-approver>"
}
```

The permission fixture must use a connection whose read access remains valid while work-item write permission is removed. The stale fixture must reference an approved recommendation whose source work-item revision was changed afterward. The PR must have an Execution Package linkage and actual changed files.

## APIs

- `POST /ado-operational-validation/run`
- `GET /ado-operational-validation/report`
- `GET /ado-operational-validation/readiness`
- `GET /ado-operational-validation/traces/{correlationId}`

Failures, retry/reconciliation results, write evidence, architecture checks, and the complete correlation timeline are returned by these APIs and persisted.

## Hard Gates

UI readiness remains blocked unless the latest report is a live, write-enabled run and all gates pass:

- read and write permissions are separated;
- writes have preview, approval, idempotency, revision protection, and audit evidence;
- PR analysis uses both the Execution Package and actual diff;
- sprint metrics use synchronized ADO data;
- failure and reconciliation states are API-visible;
- the target is non-production;
- Phase 6 routes and the SDK boundary remain stable.

## Contract Tests

```bash
bin/test-azure-devops-phase6
```

This command validates the Phase 6 contracts and operational gate mechanics. It does not replace the live run.
