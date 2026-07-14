import { HEISdk } from "../src";

export async function loadReleaseContext(sdk: HEISdk, packageId: string) {
  const executionPackage = await sdk.execution.getExecutionPackage(packageId);
  const validation = await sdk.validation.validateImplementation({ executionPackage: executionPackage.data });
  const memory = await sdk.memory.suggestReuse({ executionPackage: executionPackage.data });
  return { executionPackage, validation, memory };
}
