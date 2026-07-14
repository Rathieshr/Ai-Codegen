# Pull Request Candidate Generator

## Purpose

The Pull Request Candidate Generator creates a deterministic, reviewable summary of an engineering outcome. It does not create a branch, commit, Git pull request, Azure DevOps pull request, or review comment.

This component is upstream of PR Review. PR Review evaluates an actual pull request; the PR Candidate Generator only prepares evidence-backed content that may later be used to create one.

## Inputs

- Engineering Diff
- Validation Result
- QA Result
- immutable Execution Manifest

## Output

`PRCandidate` contains:

- summary and classified change type
- changed files from Engineering Diff paths only
- changed modules
- acceptance coverage
- risks
- breaking changes
- migration notes
- testing summary
- architecture notes
- release notes
- confidence and warnings
- source lineage
- explicit safety diagnostics

Supported change types are:

- Small Change
- Large Feature
- Refactor
- Bug Fix
- Documentation

## Evidence rules

- Changed files are included only when Engineering Diff provides a path. Missing paths produce a warning; paths are never inferred from Execution Manifest repository context.
- Acceptance coverage comes from Validation and QA results, mapped to Execution Manifest acceptance criteria.
- Breaking changes come only from semantic `breakingChanges` evidence.
- Migration notes come only from database and configuration changes.
- Architecture notes come only from architecture changes.
- Testing summary comes only from Validation and QA evidence.
- Release notes summarize semantic change counts without inventing implementation behavior.

## Readiness

- `Draft`: Validation and QA are acceptable and acceptance coverage is at least 80%.
- `NeedsReview`: acceptance coverage is weak or QA reports warnings or additional testing.
- `Blocked`: Validation or QA failed or is blocked.

Readiness does not create or reject a pull request. It describes the candidate review state.

## Safety boundary

Every candidate records:

- `created: false`
- empty `pullRequestId`
- `gitOperations: 0`
- `repositoryWrites: 0`
- `azureDevOpsWrites: 0`
- `pullRequestsCreated: 0`
- `providerCalls: 0`

The generator has no dependency on `PRReviewEngine`, Git transports, or Azure DevOps clients.

## Event

`PRCandidateCreated` is published after the candidate is persisted. The event states that a review artifact exists, not that a pull request was created.

## APIs

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/pr-candidates/generate` | Generate and persist a Pull Request candidate. |
| `GET` | `/pr-candidates` | List persisted candidates. |
| `GET` | `/pr-candidates/{id}` | Retrieve one candidate. |
