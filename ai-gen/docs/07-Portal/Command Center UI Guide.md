# Command Center UI Guide

Command Center V1 is an operating console, not a report page.

## Layout

- Keep global navigation, search, notifications, user controls, content, and the status bar stable.
- Load a workspace only after selection. Do not preload every center.
- Use compact metric grids for operational summaries and progressive disclosure for diagnostics.
- Render large activity collections in bounded windows. `Load More Activity` extends the window without mounting the entire history.
- Use responsive grids that collapse to one column below narrow tablet widths.

## Status Language

- **Healthy**: the service responded and reports a ready state.
- **Degraded**: one or more optional probes failed or require attention.
- **Unavailable**: the authoritative service could not respond.
- **Not Registered**: the service is intentionally not configured.
- **Offline**: the browser has no network connection; retain the last rendered snapshot.

## Accessibility

All workspaces require named regions, keyboard focus indicators, native buttons and controls, `aria-live` for changing health, and visible disabled states. Command palette remains available through `Ctrl/Cmd+K`; `/` focuses global search.

## Refresh

Operational health refreshes every 30 seconds only while the document is visible and online. Explicit **Refresh Now** bypasses the 10-second backend cache. Background failures never interrupt active planning or execution work.
