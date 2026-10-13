# Azure DevOps Automation Policy

## Human Control

Agents prepare work. Humans approve. The approved automation service applies only allow-listed commands.

Every write requires:

1. An approved Planning Pack, recommendation, or PR comment preview.
2. A connected Azure DevOps connection with the required write permission.
3. A source revision that still matches the approved revision.
4. An executor, reason, correlation ID, and idempotency key.
5. An authorization audit record before obtaining the write client.

## Preview First

Planning-pack and recommendation writes expose separate preview and apply operations. Preview resolves commands, current values, hierarchy links, permission requirements, warnings, and revision conflicts without writing.

There is no generic JSON Patch endpoint. Supported commands are limited to Epic, Feature, Story, and Task creation; approved field changes; hierarchy links; estimates; tags; area/iteration paths; and comments.

PR comments are stored as drafts first. Posting requires explicit approval, a contributor permission, an idempotency key, and audit availability. HEI never approves or merges pull requests.

## Failure Rules

- Authentication and authorization failures are not retried.
- A stale source revision stops the command and requires re-review.
- Partial execution stores completed command IDs and external IDs.
- Retry resumes after the last completed command and does not recreate parents or links.
- A duplicate idempotency key returns the prior result.
- Production project IDs are rejected by the Phase 6.9 hardening runner.

## Live Hardening

Live writes require both process-level and request-level approval. Use only an isolated test project. Never enable `AI_GEN_ADO_TEST_WRITES` in a production deployment or against a project listed in `AI_GEN_ADO_PRODUCTION_PROJECT_IDS`.
