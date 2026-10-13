# Azure DevOps Center

## Purpose

Azure DevOps Center is the read-only operational workspace for synchronized Azure DevOps intelligence. It presents engineering flow without replacing Azure DevOps as the system of record.

## Data Flow

```text
Azure DevOps
  -> Azure DevOps integration and centralized synchronization
  -> normalized HEI cache
  -> Sprint, work-item, PR, build, recommendation, and action-pack intelligence
  -> Azure DevOps Center projection
```

The center does not call Azure DevOps directly and does not expose write operations. Recommendation review and action approval open the shared Approval Center. Approved automation remains responsible for revision checks, idempotency, audit, and Azure DevOps writes.

## Views

- **Sprint**: current iteration, forecast, confidence, scope, velocity, and burndown.
- **Work Items**: searchable synchronized work with state, ownership, estimate, blockers, and recommendation counts.
- **Pull Requests**: synchronized PR state enriched by HEI PR Intelligence.
- **Recommendations**: pending work-item intelligence routed to human review.
- **Delivery**: blocked work, delivery risk, builds, releases, and Azure DevOps action packs.

## APIs

- `GET /ado/dashboard`
- `GET /ado/sprint`
- `GET /ado/work-items`
- `GET /ado/prs`

All endpoints accept `projectId`. Work-item and PR endpoints also support bounded pagination with `offset` and `limit`; the maximum page size is 250.

## Empty And Failure States

- A disconnected integration returns `connected: false` and an `ado_disconnected` warning.
- A project with no current iteration returns `status: NoSprint` and an empty burndown series.
- Previously synchronized data may remain visible when a connection is unavailable and is marked with a cached-data warning.
- Releases are shown only when release data exists in the synchronized cache. The center does not invent release records.
- External links are enabled only when the synchronized record contains a source URL.

## Permissions

All HEI roles may view Azure DevOps Center. Contributors and administrators may open the Approval Center. Viewers remain read-only.
