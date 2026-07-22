# Planning Workspace

The Planning Workspace is the single review and refinement surface for a Planning Pack. It reuses persisted planning artifacts, approval rules, repository evidence, and estimation contracts; it does not introduce a parallel planning engine.

## Workspace Structure

- **Header:** pack name, lifecycle status, confidence, repository, version, and last update.
- **Overview:** executive planning context, scope metrics, repository reuse, requirement quality, readiness, recent changes, and hierarchy/estimate distributions.
- **Hierarchy:** searchable, filterable Requirement, Epic, Feature, Story, and Task editor with drag/drop, reordering, manual edits, scoped regeneration, split, merge, duplicate, and archive actions.
- **Traceability:** parent lineage, children, evidence, and source references.
- **Dependencies:** Tree, Graph, and Table views for `Depends On` and `Blocked By` links, critical path, and actionable integrity warnings.
- **Estimate:** pack-level engineering days, hours, story points, sprint count, developers, confidence, risk, complexity, and estimation drivers.
- **Review:** editable title and description for Draft or Review artifacts.
- **Diff:** Git-style create, modify, keep, and ignore decisions against synchronized Azure DevOps work. The current diff must be approved before synchronization.
- **Approval:** approval readiness, comments, approver, decision actions, and version history.
- **Action panel and footer:** Generate, Save Draft, the current lifecycle action, and Export use the same action contract.

## Lifecycle

The visible lifecycle is `Draft`, `Review`, `Approved`, `Published`, `Rejected`, and `Archived`.

Draft and Review artifacts are editable. Each save increments the version and retains the previous title, payload, state, actor, and timestamp in artifact history. An optional expected version prevents one browser session from overwriting newer work.

Approved and Published artifacts cannot be edited through the workspace. Rejected planning retains its decision evidence; Archived is reserved for obsolete or removed planning. Azure DevOps work items remain owned by Azure DevOps and can only be changed through approved automation commands.

## Planning Approval

Every lifecycle decision records the actor, comments, timestamp, current version, and a complete prior snapshot. Optimistic version checks prevent stale browser sessions from applying a decision over newer planning.

- **Approve** accepts a Draft or Review version after its Engineering Estimate is available.
- **Reject** records a rejected decision and requires comments.
- **Request Changes** returns Review, Approved, or Rejected planning to a new editable Draft version.
- **Publish** marks an Approved Planning Pack ready for downstream Azure DevOps synchronization.
- **Rollback** restores a prior snapshot into a new Draft version. Newer versions remain available in Approval History.

## Hierarchy Editing

Hierarchy operations use the artifact repository rather than a client-only tree. Manual edits, parent moves, and sibling reorder operations increment node versions and reject stale browser writes. Parent changes enforce `Requirement -> Epic -> Feature -> Story -> Task`, reject cycles, and refuse to reorder immutable siblings.

Regeneration is scoped to the selected node and runs through Intent, Capability, Planning, Reasoning, and Validation Intelligence before saving a new Review version. It does not regenerate siblings or descendants. Split and merge are restricted to leaf nodes so existing child lineage cannot be orphaned. Delete archives the node; subtree deletion requires explicit cascade confirmation.

## Dependency Management

The Dependencies tab resolves one canonical link model into Tree, Graph, and Table views. Links are stored on the source planning artifact and versioned through the same Draft/Review lifecycle as hierarchy edits. Legacy dependency names remain readable but are marked as imported until replaced by a canonical artifact link.

Execution order runs from prerequisite to dependent. The workspace calculates the longest weighted path using engineering days, story points, or engineering hours in that order. Circular links are blocking and are excluded from this calculation. Missing targets remain visible for repair, while links to archived or rejected artifacts are marked broken; HEI never invents a target to complete the graph.

## Engineering Estimate

The Estimate tab always evaluates the complete Planning Pack subtree, regardless of which child is selected in the hierarchy. It displays the effective delivery estimate alongside the immutable AI estimate. Manual overrides require an engineering reason and may adjust days, hours, story points, sprint count, developers needed, confidence, risk, and complexity.

Each override retains the AI estimate, actor, timestamp, reason, and revision history. Optimistic override revisions prevent a stale browser from overwriting a newer engineering decision. Engineering days and hours use an eight-hour planning day and must remain consistent when both are supplied.

## Story Detail Drawer

Selecting a Story opens its detail drawer beside the hierarchy. The hierarchy tree, expansion state, filters, and current Planning tab remain mounted, so Story review does not navigate away from the Planning Workspace.

The drawer joins the canonical Story artifact with its acceptance criteria, business rules, dependencies, engineering estimate, story points, risks, repository modules, sibling relationships, generated Tasks, generated Tests, and engineering notes. Draft and Review content can be edited and saved with optimistic version checks. Approved Story, Task, and Test artifacts are read-only.

`Regenerate Story` uses the established Planning Intelligence pipeline. `Regenerate Tasks` replaces draft Task recommendations while retaining approved Tasks. `Generate Tests` uses QA Intelligence and persists a versioned draft Test Suite. Deleting a Story explicitly archives its generated child artifacts as one cascade operation.

## Responsive Behavior

On desktop, the selected tab uses the main content area and a sticky action panel. The footer provides the same stable lifecycle actions. On smaller screens, the action rail collapses and the footer remains available without requiring horizontal page scrolling.

## Executive Overview

`GET /planning/{id}/overview` joins the persisted Planning Pack, approved Requirement Summary, scoped child hierarchy, and latest Engineering Estimate. It is a read-only projection and never invokes Planning Intelligence, repository analysis, estimation, or an AI provider on page load.

Counts use persisted descendant artifacts first and fall back to the Planning Pack's embedded recommended hierarchy before children are materialized. Repository evidence and quality values retain their approved Requirement Summary lineage. Story and task distributions use parent-child relationships; estimate breakdown uses persisted task estimates.
# Task Generation

The Story Detail drawer owns Task planning. Users can add manual Tasks or generate AI Tasks without leaving the hierarchy. Tasks are displayed as a responsive grid and expose category, description, estimate, owner, priority, delivery status, and dependencies.

Draft and Review Tasks can be edited, regenerated, split, merged, or deleted. Approved Tasks remain read-only. Task generation remains available after Story approval because Tasks have their own approval lifecycle.
