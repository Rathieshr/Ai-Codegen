/**
 * pipelineClient.ts
 *
 * Phase 2 — VS Code Live Feedback Loop
 *
 * Provides:
 *   - `PipelineClient`  : polls `/pending-review` and pushes VS Code events
 *   - `startPipelinePoller` : creates a 30-second polling loop
 *   - `sendVsCodeEvent`     : fire-and-forget event sender
 *
 * Event types
 * -----------
 * | event_type      | When fired                                          |
 * |-----------------|-----------------------------------------------------|
 * | file_saved      | onDidSaveTextDocument (dev stage only)               |
 * | code_generated  | After Copilot/inline-chat accepts a suggestion       |
 * | test_run        | After the test runner fires (future integration)     |
 * | user_comment    | User types a note in the feedback input box          |
 * | mark_ready      | User clicks "Mark Ready" in the sidebar              |
 */

import * as vscode from 'vscode';
import * as crypto from 'crypto';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface PendingStage {
  stage: string;
  status: string;
  has_unresolved_findings: boolean;
  handoff_id: string | null;
  version: number;
}

export interface PendingReviewResponse {
  pipeline_id: string;
  work_item_id: string;
  current_stage: string;
  pending_stages: PendingStage[];
  has_pending: boolean;
  guardrail_warnings: unknown[];
}

export interface VsCodeEvent {
  event_type: 'file_saved' | 'test_run' | 'code_generated' | 'user_comment' | 'mark_ready';
  stage?: string;
  payload?: Record<string, unknown>;
  author?: string;
}

// ─── Polling interval ─────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 30_000;

// ─── PipelineClient ───────────────────────────────────────────────────────────

export class PipelineClient {
  private readonly backendUrl: string;
  private readonly pipelineId: string;
  private readonly apiKey?: string;

  constructor(backendUrl: string, pipelineId: string, apiKey?: string) {
    this.backendUrl = backendUrl.replace(/\/+$/, '');
    this.pipelineId = pipelineId;
    this.apiKey = apiKey;
  }

  /** Return stages waiting for human approval. */
  async getPendingReview(): Promise<PendingReviewResponse | null> {
    const url = `${this.backendUrl}/assist/pipeline/${encodeURIComponent(this.pipelineId)}/pending-review`;
    try {
      const response = await fetch(url, { method: 'GET', headers: this._headers() });
      if (!response.ok) { return null; }
      return await response.json() as PendingReviewResponse;
    } catch {
      return null;
    }
  }

  /** Push an event from VS Code into the pipeline. */
  async sendEvent(event: VsCodeEvent): Promise<boolean> {
    const url = `${this.backendUrl}/assist/pipeline/${encodeURIComponent(this.pipelineId)}/vscode-event`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...this._headers() },
        body: JSON.stringify(event),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  private _headers(): Record<string, string> {
    return this.apiKey ? { 'X-Api-Key': this.apiKey } : {};
  }
}

// ─── Poller ───────────────────────────────────────────────────────────────────

/**
 * Start a 30-second polling loop.
 *
 * @returns A `Disposable` that stops the poller when disposed.
 */
export function startPipelinePoller(
  client: PipelineClient,
  onPending: (stages: PendingStage[]) => void,
): vscode.Disposable {
  let timer: ReturnType<typeof setInterval> | undefined;

  const poll = async () => {
    const result = await client.getPendingReview();
    if (result?.has_pending && result.pending_stages.length > 0) {
      onPending(result.pending_stages);
    }
  };

  // Initial poll immediately, then every 30s
  void poll();
  timer = setInterval(() => { void poll(); }, POLL_INTERVAL_MS);

  return new vscode.Disposable(() => {
    if (timer !== undefined) {
      clearInterval(timer);
      timer = undefined;
    }
  });
}

// ─── File-save hook ───────────────────────────────────────────────────────────

/**
 * Register an onDidSaveTextDocument listener that pushes a `file_saved` event
 * to the backend when the developer saves a file that is relevant to an active
 * DEV stage (files tracked by the pipeline).
 *
 * @param client     The PipelineClient for the active pipeline.
 * @param trackedFiles  Set of file paths tracked by the current DEV stage.
 *                      Pass an empty set to track all saves.
 * @returns A `Disposable` that removes the listener.
 */
export function registerFileSaveHook(
  client: PipelineClient,
  activeStage: string,
  trackedFiles: Set<string> = new Set(),
): vscode.Disposable {
  return vscode.workspace.onDidSaveTextDocument(async (doc) => {
    const filePath = doc.uri.fsPath;

    // Only track if relevant to the active pipeline stage
    if (trackedFiles.size > 0 && !trackedFiles.has(filePath)) {
      return;
    }

    // Compute a lightweight content hash for drift detection
    const contentHash = crypto
      .createHash('sha256')
      .update(doc.getText())
      .digest('hex')
      .substring(0, 12);

    await client.sendEvent({
      event_type: 'file_saved',
      stage: activeStage,
      payload: {
        file_path: filePath,
        language_id: doc.languageId,
        content_hash: contentHash,
        line_count: doc.lineCount,
      },
    });
  });
}

// ─── Notification helper ──────────────────────────────────────────────────────

/**
 * Show a VS Code notification for each pending stage.
 * The user can click "Open Sidebar" to navigate to the ai-gen panel.
 */
export async function notifyPendingStages(stages: PendingStage[]): Promise<void> {
  if (stages.length === 0) { return; }

  const stageNames = stages.map((s) => s.stage).join(', ');
  const label = stages.length === 1
    ? `ai-gen: Stage "${stageNames}" is ready for review.`
    : `ai-gen: ${stages.length} stages ready for review (${stageNames}).`;

  const action = await vscode.window.showInformationMessage(label, 'Open Sidebar');
  if (action === 'Open Sidebar') {
    await vscode.commands.executeCommand('workbench.view.extension.aiGen');
  }
}
