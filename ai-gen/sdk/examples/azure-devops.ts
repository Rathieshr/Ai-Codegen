import { HEISdk } from "../src";

export async function analyzeSelectedWorkItem(sdk: HEISdk, workItem: Record<string, unknown>) {
  return sdk.azureDevOps.analyzeWorkItem(workItem, { correlationId: `ado-${String(workItem.id ?? "new")}` });
}
