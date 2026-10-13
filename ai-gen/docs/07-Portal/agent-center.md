# Agent Center

## Purpose

Agent Center is the operational view of HEI's agent runtime. It explains what each agent is doing, what is queued, what failed, and where human review is required.

Agents remain preparation-only. Agent Center does not approve artifacts, merge pull requests, modify repositories, or bypass governance policies.

## Data Sources

```text
Agent Registry and Feature Flags
  + Orchestrator Workflows
  + Platform Job Queue
  + Platform Agent Runtime Runs
  + Azure DevOps Agent Runs
  + Platform Activity
  -> Agent Center projection
```

The projection normalizes the Planning, Repository, Execution, Validation, QA, Review, Memory, and ADO agents without fabricating activity for agents that have not run.

## Status Model

- **Idle**: enabled with no running, queued, or latest failed work.
- **Running**: at least one current workflow, job, or runtime run is active.
- **Queued**: work is queued, pending, or waiting at an approval boundary.
- **Failed**: the latest recorded work failed and no newer active work supersedes it.
- **Disabled**: the agent feature flag is off.

Health, success rate, average duration, failures, queue size, last run, and next run are derived only from recorded data. Missing schedules display `Not scheduled`; missing history displays `Not measured` or `Never run`.

## APIs

- `GET /agents`
- `GET /agents/{id}`
- `GET /agents/{id}/jobs`
- `GET /agents/{id}/health`
- `POST /agents/jobs/{jobId}/retry`

Job listing is paginated and capped at 250 records per request. Retry accepts only failed orchestrator workflows or failed platform jobs. Runtime records without a replayable job are read-only.

## User Operations

- **View Details** opens responsibilities, triggers, actions, approval boundary, warnings, and diagnostics.
- **Retry Failed Job** retries only an eligible recorded failure.
- **Open Activity** opens the shared activity workspace.
- **View Logs** shows matching platform activity without exposing raw logs in the default view.

## Trust Rules

- Historical failures remain visible but do not override a newer successful or active run.
- Disabled agents are reported as disabled rather than unhealthy.
- Empty queues and missing schedules are explicit.
- Human approval boundaries remain visible on every agent.
