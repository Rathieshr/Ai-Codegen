# Azure DevOps Sprint Intelligence

## Purpose

Sprint Intelligence explains engineering flow using the centralized Azure DevOps synchronization cache. It produces metrics, delivery risks, forecasts, and recommended interventions. It does not update sprint scope, assign work, rank developers, or perform autonomous sprint management.

## Sources

The report consumes normalized, synchronized records only:

- iterations for identity, dates, and optional configured capacity;
- work items for scope, state, estimates, dates, dependencies, tags, and reopen signals;
- pull requests for linked review waiting time;
- builds for sprint-window reliability signals;
- Estimation Intelligence for project/team calibration.

Missing data is represented explicitly. HEI does not infer file activity, work hours, developer effort, or hidden Azure DevOps history.
When team capacity is not synchronized, capacity comparison is returned as `NotEvaluated`; HEI does not assume capacity.

## Metrics

Each report includes:

- planned, completed, and remaining scope as item counts and story points;
- daily burndown reconstructed from synchronized creation and closure dates;
- current velocity and available historical sprint average;
- carryover based on pre-sprint creation dates;
- blocked and aging work;
- active PR waiting time;
- build failures;
- reopened work;
- estimation accuracy;
- a range-free completion forecast with an explicit evidence-based confidence score.

When estimates are unavailable, item counts remain visible and confidence is reduced. Forecast dates are omitted when there is no completed scope from which to calculate a defensible rate.

## Risk Signals

The deterministic risk engine detects:

- too much work in progress;
- late scope additions, using the first revision that entered the sprint when revision history is available;
- blocked dependencies;
- PR review bottlenecks;
- high-risk work without synchronized Test Cases;
- repeated build failures;
- large unfinished stories;
- stale tasks;
- configured capacity mismatch.

Every signal contains severity, reason, and work-item/build/PR evidence. Recommendations address the flow condition rather than evaluating an individual.

## Privacy Boundary

Reports contain a permanent `privacy` section declaring `EngineeringFlowOnly` mode. HEI does not calculate or expose rankings based on commits, lines of code, keyboard activity, or hours online. Assignment data is not copied into Sprint Intelligence reports.

## Health and Forecast

Health values are:

- `Healthy`
- `NeedsAttention`
- `AtRisk`
- `Completed`
- `InsufficientData`

Forecast status is `OnTrack`, `AtRisk`, `Completed`, or `InsufficientData`. A forecast is an observed-flow projection, not a commitment. Confidence is reduced by missing estimates, dates, history, and completed activity.

## APIs

- `GET /ado-intelligence/projects/{projectId}/sprints/current`
- `GET /ado-intelligence/projects/{projectId}/sprints/{iterationId}/report`
- `GET /ado-intelligence/projects/{projectId}/sprints/{iterationId}/burndown`
- `GET /ado-intelligence/projects/{projectId}/sprints/{iterationId}/risks`

All endpoints are read-only. `teamId` is an optional query parameter for team-scoped work and calibration where synchronized data supports it.
