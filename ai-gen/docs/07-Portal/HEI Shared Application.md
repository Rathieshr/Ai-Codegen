# HEI Shared Application

## Architecture

The HEI React application is host-independent:

```text
Azure DevOps Host Adapter ─┐
                          ├─ HEI Application Shell ─ Internal Router ─ Shared Views ─ HEI APIs
Standalone Host Adapter ──┘
```

The shell provides the header, sidebar, workspace context, notifications, status bar, user menu, theme, command palette, global search, and content region. Views receive normalized host context and backend service URLs; they do not call the Azure DevOps Extension SDK.

## Navigation

Internal navigation uses history state and query parameters. Each page is lazy-loaded on selection. Azure DevOps remains loaded around the HEI iframe.

Notifications may include a `target` route. Selecting one closes the notification panel and opens its internal HEI page.

## Developer Guide

Add a new shared workspace by:

1. Creating a host-independent React component.
2. Adding a lazy import and route in `heiApp.tsx`.
3. Adding role visibility in `navigationFor()`.
4. Using HEI backend APIs rather than Azure DevOps SDK calls.
5. Adding the route to the single-hub regression test.

Do not add another Azure DevOps hub contribution for an internal HEI workspace.

Standalone development uses `?host=standalone` with optional `projectId`, `project`, `repositoryId`, `repository`, `branch`, `userId`, and `role` query parameters.
