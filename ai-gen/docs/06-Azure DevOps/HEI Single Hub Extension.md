# HEI Azure DevOps Single Hub

## Purpose

HEI is installed as one project-level Azure DevOps application. The Azure DevOps contribution hosts the HEI React application; HEI owns all navigation after startup.

## Contribution Model

The `azure-devops-extension.hei.json` manifest contains:

- one project hub group named `HEI`;
- one `ms.vss-web.hub` contribution named `HEI`;
- the existing work-item form page;
- one work-item toolbar action named `Open in HEI`.

The hub loads `dist/hei/index.html`. Planning, Repository, Execution, Approvals, Azure DevOps Intelligence, Agents, Activity, and Settings are internal routes, not Azure DevOps contributions.

## Host Adapter

`AzureDevOpsHostAdapter` is the only HEI hub module that imports the Azure DevOps Extension SDK. It initializes the SDK and resolves organization, project, team, user, extension, route, repository hints, theme, and correlation ID into `HEIHostContext`.

`StandaloneHostAdapter` implements the same contract using browser and authentication context. Shared views, state, routing, validation, and backend services do not depend on the host.

Access tokens are requested only through the host adapter and are not placed in application state or sent with diagnostics.

## Routing

The hub uses browser history routing inside its iframe. Navigation updates `view`, `workItemId`, and `repositoryId` query parameters with `history.pushState`; it does not reload Azure DevOps.

Supported routes:

- `overview`
- `new-requirement`
- `planning`
- `repository`
- `execution`
- `approvals`
- `azure-devops`
- `agents`
- `activity`
- `settings`

Work-item deep links target the full contribution ID:

`AiIntelliCodegen.hei-engineering-platform.hei-command-center`

They pass `view=planning` and `workItemId=<id>`. The Planning Center selects the synchronized item when available.

## Requirement Intake

New Requirement supports Business Requirement, PRD, BRD, Meeting Notes, Bug Report, Azure DevOps Work Item, and Customer Request inputs.

`POST /requirements/intake` sends the requirement through the shared Context Orchestrator with Planning, Repository Intelligence, Knowledge Registry, and Engineering Memory enabled. The result is a draft Planning Pack with approval required. Intake never writes to Azure DevOps.

## Permissions

Navigation is reduced by the normalized host role:

- Viewers receive Overview, Planning, Repository, Execution, Azure DevOps, and Activity.
- Contributors also receive New Requirement, Approvals, and Agents.
- Administrators additionally receive Settings.

Backend authorization remains authoritative for every operation. Hiding navigation is a usability measure, not a security boundary.

## Theme

Azure DevOps applies its theme through the Extension SDK. The host adapter observes theme changes and supports light, dark, and high-contrast modes. Shared UI uses HEI theme variables rather than host-specific styling.

## Diagnostics

The SPA records hub load, workspace load failures, internal navigation, theme changes, startup duration, host type, project, and correlation ID through `POST /workspace/diagnostics`. Diagnostic failure never blocks the hub.

## Deployment

Run `npm run package:hei`. Upload the generated private VSIX to the test organization. Share it with the organization and enable the extension for a test project. The existing AI Gen extensions can remain installed because HEI uses an independent extension ID.

Before publishing an update, increment the version in `azure-devops-extension.hei.json` while preserving extension and contribution IDs.
