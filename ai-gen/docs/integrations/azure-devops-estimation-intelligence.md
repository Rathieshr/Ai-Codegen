# Azure DevOps Estimation and Dependency Intelligence

## Purpose

HEI recommends relative story points, engineering effort ranges, task decomposition, dependencies, and uncertainty for synchronized Azure DevOps work items. Azure DevOps remains the system of record. Estimation Intelligence does not update work items directly.

## Inputs

The estimator uses the current synchronized work-item revision and, when available:

- acceptance criteria and prior decomposition;
- repository mode, relevant modules, and ranked files;
- explicit and linked dependencies;
- similar completed work in the same project;
- accepted Engineering Memory as supporting evidence;
- recorded estimate outcomes and team configuration.

Repository facts take precedence over Engineering Memory and historical similarity. Missing repository evidence is reported as uncertainty rather than replaced with invented files or modules.

## Output

An estimate includes:

- three to eight suggested tasks;
- Fibonacci story points: `1`, `2`, `3`, `5`, `8`, or `13`;
- development, QA, and review effort ranges;
- dependencies, blockers, and assumptions;
- similar historical items and evidence;
- confidence and explicit uncertainty reasons;
- project/team calibration diagnostics.

Time is always represented as a coarse range, such as `2-4 days`. Story points express relative complexity and are not converted into precise hours or used to score individual engineers.

## Calibration

Calibration compares previous recommendations with recorded outcomes:

- actual cycle time;
- actual active time when available;
- reopen count;
- pull-request iterations;
- escaped defects.

At least three completed outcomes are required. Team calibration is used only when a team has enough samples; otherwise HEI falls back to project calibration. With fewer than three project samples, the result is `Uncalibrated` and confidence remains conservative.

Calibration describes estimation bias and flow quality. It does not rank developers or use commits, lines of code, keyboard activity, or online time.

## Human Decisions

Recommendations support these actions through the estimate endpoint:

- `generate` or `regenerate`;
- `edit` with an approved Fibonacci point value and edit reason;
- `accept`;
- `reject`;
- `recordOutcome` after completion.

Editing creates a new version linked to the prior estimate. Accepting creates an approved `StoryPointRecommendation` for the Azure DevOps Automation layer. The automation layer still requires preview, revision validation, permission checks, idempotency, and audit before any write.

If the synchronized work-item revision changes, the estimate becomes `Stale` and cannot be accepted until regenerated.

## APIs

### Generate or decide

`POST /ado-intelligence/work-items/{id}/estimate`

Generate example:

```json
{
  "projectId": "project-id",
  "teamId": "team-id",
  "repositoryImpact": {
    "mode": "CodeIndexed",
    "modules": ["Asset Health"],
    "files": ["ranked-file-from-repository-intelligence"]
  }
}
```

Decision example:

```json
{
  "action": "accept",
  "estimateId": "estimate-id",
  "actor": "product-owner"
}
```

### Read latest recommendation

`GET /ado-intelligence/work-items/{id}/estimate?projectId={projectId}`

### Read calibration

`GET /ado-intelligence/projects/{id}/estimation-accuracy?teamId={teamId}`

## Limitations

- Historical calibration is useful only when outcome data is consistently recorded.
- Cycle-time history may reflect queueing and organizational delay, not only implementation effort.
- A high-confidence estimate is still a recommendation requiring team review.
- Repository-unavailable mode produces lower confidence and a manual repository-impact blocker.
