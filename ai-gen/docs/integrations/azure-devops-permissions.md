# Azure DevOps Permissions

## Minimum Read Scopes

Use a read-only connection for synchronization and intelligence:

- Project and Team: Read
- Work Items: Read
- Code and Pull Requests: Read
- Build: Read

The read client contains no create, update, delete, approve, merge, or build-queue operation.

## Write Scopes

Use a separate connection or secret reference for approved automation:

- Work Items: Read and Write for approved hierarchy and field commands
- Pull Request Threads: Contribute for approved HEI comments

HEI does not require permission to approve or merge pull requests, delete work items, rewrite Git history, queue deployments, or administer project security.

## Credential Handling

Connection records store a `secretReference`, never a PAT, token, password, client secret, or authorization header. The credential provider resolves the secret at request time. Public connection APIs omit both plaintext credentials and the secret reference.

Rotate credentials in the backing secret store. Validation reports only status and a safe message.

## Project Isolation

All synchronized cache records, mappings, recommendations, estimates, PR reports, sprint reports, action packs, and hardening reports are scoped by project and connection identifiers. A project identifier is required when an external ID can be ambiguous across organizations.

## Test Project Permission Matrix

| Scenario | Read | Write |
| --- | --- | --- |
| Sync, analysis, estimation, sprint report | Required | Not required |
| Planning Pack preview | Required | Permission checked, no write |
| Hierarchy application | Required | Work Items Write |
| PR analysis and comment preview | Required | Not required |
| Approved PR comment | Required | Pull Request Threads Contribute |

Permission-loss tests must use a dedicated connection lacking the targeted write permission. They pass only when HEI stops before a write client is used.
