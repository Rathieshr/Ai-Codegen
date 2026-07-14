# Azure DevOps Integration

## Phase 6 Boundary

Azure DevOps remains the system of record. HEI synchronizes normalized project, team, iteration, work-item, repository, pull-request, and build data; intelligence results and approval state remain HEI-owned.

```text
Azure DevOps
  -> read and approved-write clients
  -> normalized integration services
  -> centralized synchronization cache
  -> work-item, estimation, PR, and sprint intelligence
  -> approved automation and Azure DevOps Agent
```

Planning, Repository Intelligence, Prompt Intelligence, Runtime, Validation, QA, and Engineering Memory must not call Azure DevOps REST APIs directly.

Operationally, Azure DevOps access follows the HEI Platform SDK boundary documented in [Azure DevOps Operational Validation](azure-devops-operational-validation.md). Phase 6.10 statically rejects direct integration/client access from intelligence modules.

## Synchronization

Initial sync establishes project-scoped normalized data. Service hooks then update changed records incrementally. A daily reconciliation checks for missed or out-of-order events without performing an unconditional full sync. Webhook receipts and sync cursors make delivery idempotent.

Repository synchronization stores metadata only. Repository Intelligence owns source indexing and graph refresh.

## Phase 6.9 Validation

Run the mocked regression suite in CI:

```bash
bin/test-azure-devops-phase6
```

The suite covers all Phase 6 service milestones and produces a hardening report through:

- `POST /ado-hardening/run`
- `GET /ado-hardening/report`
- `GET /ado-hardening/runs`
- `GET /ado-hardening/runs/{runId}`
- `GET /ado-hardening/readiness`

Command Center readiness requires all ten end-to-end scenarios plus security, reliability, performance, and write-safety gates.

Phase 6.10 then requires nine live operational flows under one correlation trace. Mocked operational validation never unlocks UI readiness.

## Live Test Project

Live validation is disabled by default. Configure an isolated non-production project with:

- `AI_GEN_ADO_LIVE_TESTS=true`
- `AI_GEN_ADO_TEST_PROJECT_IDS=<allowed project IDs>`
- `AI_GEN_ADO_PRODUCTION_PROJECT_IDS=<blocked production IDs>`
- `AI_GEN_ADO_TEST_PROJECT_ID`, connection, repository, work-item, PR, iteration, and fixture IDs described in troubleshooting

Writes require the additional `AI_GEN_ADO_TEST_WRITES=true` switch and a request whose `projectConfirmation` exactly matches `projectId`. Preview-only live validation is the default.

## Performance Baselines

Each report records initial and incremental synchronization, work-item analysis, estimation, hierarchy preview/application, PR analysis, sprint reporting, and agent response timings. Baselines are compared only within the same mode and test environment; mock timings are not presented as Azure DevOps network performance.
