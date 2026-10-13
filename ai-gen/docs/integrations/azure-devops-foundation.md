# Azure DevOps Integration Foundation

## Purpose

The Azure DevOps integration is HEI's read-only boundary to the Azure DevOps system of record. Planning, Repository, Prompt, Runtime, Validation, QA, and Engineering Memory consume normalized operations through the HEI Platform SDK; they do not call Azure DevOps REST APIs directly.

```text
Azure DevOps
  -> Azure DevOps Integration Layer
  -> HEI Platform SDK
  -> HEI Intelligence Services
```

Milestone 6.1 does not create or modify work items, repositories, pull requests, builds, releases, teams, or iterations.

## Module Architecture

`backend/integrations/azure_devops/` contains:

- `domain`: connections, normalized external models, and typed errors.
- `application`: business-oriented service contracts and read orchestration.
- `infrastructure`: credential resolution, resilient HTTP reads, pagination, and JSON-backed connection storage.
- `mapping`: provider DTO to HEI model mapping.
- `api`: connection and discovery routes.
- `bootstrap.py`: dependency registration.

The older `backend/ado` automation adapter remains a legacy write-capable boundary. New intelligence and client work must use the integration module and Platform SDK. A later migration milestone can retire direct legacy consumers without mixing that risk into this read-only foundation.

## Authentication And Secrets

PAT authentication is available for development. OAuth with Microsoft Entra ID and Managed Identity are modeled as future credential-provider modes.

Connections persist only `secretReference`. The reference points to secure process configuration; the credential value is resolved at request time and is never returned by an API. Requests containing `pat`, `token`, `password`, `secret`, `clientSecret`, or similar plaintext fields are rejected.

Recommended PAT permissions are read-only and limited to the required operations:

- Project and Team: read
- Work Items: read
- Code and Pull Requests: read
- Build: read

## Supported Read Operations

- Register, list, inspect, validate, and check connection health.
- Discover the configured organization, projects, and teams.
- List iterations and resolve the current sprint.
- Execute read-only WIQL and retrieve hierarchy and revisions.
- List repositories and repository metadata.
- List pull requests and retrieve pull-request details.
- List builds and statuses.
- Normalize incoming service-hook notifications.

## API

Required connection routes:

- `POST /integrations/azure-devops/connections`
- `GET /integrations/azure-devops/connections`
- `GET /integrations/azure-devops/connections/{id}`
- `POST /integrations/azure-devops/connections/{id}/validate`
- `GET /integrations/azure-devops/connections/{id}/projects`
- `GET /integrations/azure-devops/connections/{id}/health`

Project-scoped routes additionally expose teams, iterations, current sprint, WIQL, work-item hierarchy/revisions, repositories, pull requests, and builds. Correlation IDs may be supplied in `X-Correlation-ID` and are propagated to Azure DevOps requests and platform events.

## Normalized Models

Provider response structures are mapped before entering HEI:

- `ExternalProject`
- `ExternalTeam`
- `ExternalIteration`
- `ExternalWorkItem` and `ExternalWorkItemLink`
- `ExternalRepository`
- `ExternalPullRequest`
- `ExternalBuild`

Raw Azure DevOps DTOs are infrastructure details and must not appear in intelligence service contracts.

## Resilience And Errors

The read client applies a configurable timeout and retries safe reads for transient timeouts, network failures, HTTP 429, and server failures. Pagination follows Azure DevOps continuation tokens. Authorization and authentication failures are never retried. Cancellation is checked before attempts and while waiting between attempts.

Typed failures include authentication, authorization, unavailable organization, rate limit, timeout, cancellation, not found, and validation. API responses expose an error code, safe message, retryability, and correlation ID without credential material.

## Platform Events

- `AzureDevOpsConnectionRegistered`
- `AzureDevOpsConnectionValidated`
- `AzureDevOpsConnectionFailed`
- `AzureDevOpsProjectDiscovered`
- `AzureDevOpsReadFailed`

Inbound service-hook normalization also emits `AzureDevOpsWebhookReceived`. No event handler writes back to Azure DevOps in this milestone.

Milestone 6.2 adds centralized cached synchronization behind the same read-only boundary. See [Azure DevOps Synchronization](azure-devops-synchronization.md) for cursors, idempotent service hooks, mappings, reconciliation, and sync diagnostics.

## Future Write Support

Write operations require a separate approved milestone with explicit policies, permission checks, approval boundaries, idempotency, audit, and dedicated write contracts. They must not be added to `AzureDevOpsReadClient`.
