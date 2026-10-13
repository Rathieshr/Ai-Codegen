import { HEISdk } from "../src";

export async function openExecutionWorkspace(sdk: HEISdk, packageId: string): Promise<string> {
  const packageResult = await sdk.execution.getExecutionPackage(packageId);
  const prompt = await sdk.prompt.generateExecutionPrompt({ executionPackage: packageResult.data, target: "Copilot" });
  return String((prompt.data as Record<string, unknown>).finalPrompt ?? "");
}

export async function startExecutionSession(
  sdk: HEISdk,
  executionPrompt: string,
  packageVersion: string,
  planVersion: string
) {
  return sdk.runtime.startExecution({
    executionPrompt,
    executionPackageVersion: packageVersion,
    executionPlanVersion: planVersion,
    provider: "Copilot",
    model: "Auto"
  });
}
