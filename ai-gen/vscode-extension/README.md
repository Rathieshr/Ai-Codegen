# ai-gen VS Code Extension

Minimal VS Code extension for sending editor context to the ai-gen backend and displaying the enriched Codex-ready prompt in a persistent sidebar. It can use a local backend or the Railway-hosted backend.

## Commands

- `ai-gen: Ask`
- `ai-gen: Explain Relevant Flow`
- `ai-gen: Generate Safely`
- `ai-gen: Copy Last Prompt`
- `ai-gen: Send Last Prompt to Codex`
- `ai-gen: Check Backend Connection`
- `ai-gen: Refresh Backend Resolution`

The command palette commands remain available, but the ai-gen Activity Bar sidebar is the main control surface.

## Backend Modes

The extension supports three backend modes through VS Code settings:

- `ai-gen.backendMode`: `auto`, `local`, or `railway`
- `ai-gen.localBackendUrl`: defaults to `http://127.0.0.1:8000`
- `ai-gen.railwayBackendUrl`: defaults to `https://ai-codegen-production.up.railway.app`

In `auto` mode, ai-gen checks the local backend first with `/health`. If local is unavailable, it checks the Railway backend. Local wins when both are healthy, which keeps development fast while still allowing team testing against Railway.

Use `local` mode to always use the local backend. Use `railway` mode to always use the Railway backend. If the selected backend is unavailable, the sidebar shows a disconnected state and a clear reason.

The Railway service listens on Railway's assigned port internally. The public extension URL should normally be the HTTPS Railway domain, not a manual localhost-style port URL.

## Start Local Backend

From the project root:

```bash
cd "/Users/macbook/Products/Ai Gen Dev/ai-gen"
.venv/bin/python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

With default `auto` mode, the extension will choose this local backend whenever `/health` succeeds.

## Install Extension Dependencies

From this folder:

```bash
npm install
npm run compile
```

## Run In VS Code

1. Open `vscode-extension/` in VS Code.
2. Run `npm install`.
3. Press `F5` to launch an Extension Development Host.
4. In the new VS Code window, open the ai-gen icon in the Activity Bar.
5. Enter a task and click `Preview`, or use `Explain`, `Copy Prompt`, `Send to Codex`, and `Check Backend`.
6. Use the generated packet with your preferred executor: Codex, Gemini, Copilot, Claude, Cursor, or manual implementation.

The existing command palette commands still work and update the same latest prompt state.

## Sidebar

The ai-gen sidebar includes:

- backend status
- backend mode, active backend source, resolved backend URL, and selection reason
- Codex availability
- local model availability when reported by the backend
- Ollama reachability, model name, local base URL, cloud status, and setup warnings
- task input
- toggles for current selection and current file
- Preview, Explain, Copy Prompt, Send to Codex, and Check Backend actions
- Executor-agnostic packets that can be used with Codex, Gemini, Copilot, Claude, Cursor, or manual implementation
- routed result summary
- flow, linked flows, impacted components, constraints, plan, local output, and final prompt sections

The sidebar loads even when the backend is offline. Use `Refresh Status`, `Check Backend`, or `ai-gen: Refresh Backend Resolution` after starting local backend or changing settings.

## Status

The sidebar first resolves the active backend with `/health`, then fetches `/capabilities` when the view opens and whenever you click `Refresh Status`.

- `Backend: Connected` means the ai-gen FastAPI backend responded.
- `Backend Mode` is the configured mode: `auto`, `local`, or `railway`.
- `Active Backend` is the resolved source: `local`, `railway`, or `none`.
- `Backend URL` is the base URL currently used for `/context`, `/capabilities`, snapshots, and validation.
- `Backend Reason` explains why the backend was selected or why resolution failed.
- `Codex: Available` means Codex is enabled by environment/config or the `codex` CLI was found on `PATH`.
- `Local: Enabled` means `AI_GEN_LOCAL_ENABLED=1`.
- `Local: Disabled` means local routing is off, even if Ollama is installed.
- `Ollama: Reachable` means local is enabled, `AI_GEN_LOCAL_PROVIDER=ollama`, and the backend can reach Ollama.
- `Model` shows `AI_GEN_LOCAL_MODEL`, or `Not configured`.

Local Enabled and Local Available are different on purpose. Local can be enabled in env but unavailable if the provider is missing, the model name is not configured, or Ollama is not running.

If Ollama is enabled but unreachable:

1. Start Ollama locally.
2. Check `AI_GEN_LOCAL_BASE_URL`, or leave it unset to use `http://localhost:11434`.
3. Set `AI_GEN_LOCAL_MODEL` to the model ai-gen should use.
4. Click `Refresh Status`.

Codex must still be installed separately and available on `PATH` for terminal execution.

## Behavior

Preview and Explain send:

- natural language query
- current file path, if any
- selected text, if any
- workspace root, if any

The extension displays the backend's `optimized_prompt` in the sidebar. Command palette preview actions now focus/update the sidebar instead of opening a separate editor preview document.

The sidebar separates, when present:

- Execution Target
- Routing Reason
- Available Targets
- Planning Enabled
- Plan Summary
- Execution Plan
- Flow
- Critical Steps
- Detected Intent
- Linked Flows
- Impacted Components
- Critical Constraints
- Final Codex Prompt

If the backend returns `local_output`, it appears under `Local Output` in the same sidebar.

## Execution Routing

The backend returns MVP routing metadata with each prompt:

- `execution_target`
- `execution_reason`
- `available_targets`

Supported targets are:

- `local`
- `cloud`
- `codex`
- `preview_only`

Current MVP limitations:

- `codex` is the only active execution path.
- `local` and `cloud` are routing-ready only; no provider calls are implemented yet.
- `preview_only` means ai-gen should only preview or copy the prompt.

The sidebar shows the selected execution target and reason near the top of the result.

## Planning

The backend can attach a small deterministic execution plan for risky or multi-step work, such as auth changes, payment logic, migrations, or refactors. The preview shows:

- whether planning was enabled
- a short plan summary
- ordered execution steps, when present

This is guidance for Codex prompt execution only. The extension does not run multi-step autonomous workflows or store plans on disk.

## Copy Prompt

Use the sidebar `Copy Prompt` button or run:

```text
ai-gen: Copy Last Prompt
```

This copies the most recent backend-generated Codex prompt to the clipboard. If no prompt has been generated yet, the extension shows a helpful error.

## Send To Codex

Use the sidebar `Send to Codex` button or run:

```text
ai-gen: Send Last Prompt to Codex
```

This command:

1. Reuses the most recent ai-gen prompt.
2. Shows a routing override confirmation if the backend did not choose `codex`.
3. Checks that the `codex` CLI is available on `PATH`.
4. Shows a final confirmation dialog.
5. Opens an integrated terminal.
6. Sends the prompt to:

```bash
codex '<enriched prompt>'
```

The extension never sends prompts to Codex automatically. Execution only happens after running `ai-gen: Send Last Prompt to Codex` and confirming the action.

## Check Backend

Use the sidebar `Check Backend` button or run:

```text
ai-gen: Check Backend Connection
```

The extension resolves the active backend, then checks capabilities from that backend. If the backend is offline, it shows a clear error and disables backend-dependent sidebar actions.

## Requirements

- ai-gen backend running locally, or the Railway backend URL configured and reachable.
- Node dependencies installed with `npm install`.
- Codex CLI installed and available on `PATH` for `ai-gen: Send Last Prompt to Codex`.

`ai-gen: Generate Safely` prepares and previews the enriched prompt in the ai-gen sidebar. It does not execute Codex by itself.
