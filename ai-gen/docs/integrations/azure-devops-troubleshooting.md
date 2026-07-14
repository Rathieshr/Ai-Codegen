# Azure DevOps Troubleshooting

## Run The Mocked Regression Suite

```bash
bin/test-azure-devops-phase6
```

This compiles backend/tests and runs Milestones 6.1 through 6.9. The optional live test is reported as skipped unless enabled.

## Live Test Configuration

The following values are required for the isolated-project runner:

```text
AI_GEN_ADO_LIVE_TESTS=true
AI_GEN_ADO_TEST_BACKEND_URL=http://localhost:8000
AI_GEN_ADO_TEST_PROJECT_IDS=<comma-separated allow-list>
AI_GEN_ADO_PRODUCTION_PROJECT_IDS=<comma-separated block-list>
AI_GEN_ADO_TEST_PROJECT_ID=<isolated project ID>
AI_GEN_ADO_TEST_CONNECTION_ID=<connected HEI connection>
AI_GEN_ADO_TEST_REPOSITORY_ID=<repository fixture>
AI_GEN_ADO_TEST_PLANNING_PACK_ID=<approved pack fixture>
AI_GEN_ADO_TEST_EPIC_ID=<Epic fixture>
AI_GEN_ADO_TEST_STORY_ID=<Story fixture>
AI_GEN_ADO_TEST_PR_ID=<PR fixture>
AI_GEN_ADO_TEST_ITERATION_ID=<sprint fixture>
AI_GEN_ADO_TEST_STALE_RECOMMENDATION_ID=<recommendation whose source changed>
AI_GEN_ADO_TEST_PERMISSION_RECOMMENDATION_ID=<permission-loss fixture>
AI_GEN_ADO_TEST_OUTAGE_CONNECTION_ID=<unavailable endpoint fixture>
```

For approved write scenarios also set `AI_GEN_ADO_TEST_WRITES=true`. The hardening request must send `projectConfirmation` equal to the project ID. The backend rejects production IDs even if they are accidentally allow-listed.

## Common Failures

### Live test safety block

Confirm live mode is enabled, the project is in the test allow-list, it is absent from the production block-list, and confirmation matches exactly. Do not weaken these checks to make a run pass.

### Authentication or permission failure

Validate the connection health and secret reference. Authentication and authorization failures are intentionally not retried. Compare the requested operation with the minimum permission matrix before adding scopes.

### Recommendation became stale

The work-item revision changed after approval. Regenerate the recommendation and obtain a new approval; HEI will not overwrite the newer ADO value.

### Duplicate webhook

A repeated event should return `duplicate: true` and should not enqueue a second synchronization. Inspect webhook receipts and correlation IDs before replaying.

### Azure DevOps outage

Safe reads retry bounded transient failures and honor rate-limit delays. After attempts are exhausted, the connection or sync records a retryable failure. Use scheduled reconciliation after recovery rather than forcing a full sync.

### Partial hierarchy application

Use the same idempotency key to resume. HEI reuses created external IDs and skips completed commands. Do not start a second Planning Pack application with a new key until the partial run is resolved.

## Hardening Report

`GET /ado-hardening/report` shows scenario evidence, security checks, reliability checks, operation baselines, quality gates, and blockers. `GET /ado-hardening/readiness` is the stable pre-Command-Center readiness contract.
