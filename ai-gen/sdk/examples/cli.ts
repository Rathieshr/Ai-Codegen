import { ApiKeyAuthenticationProvider, HEISdk } from "../src";

async function main(): Promise<void> {
  const sdk = new HEISdk(
    { baseUrl: process.env.HEI_BASE_URL ?? "http://127.0.0.1:8000" },
    { authentication: new ApiKeyAuthenticationProvider(process.env.HEI_API_KEY ?? "development") }
  );
  await sdk.initialize();
  const planning = await sdk.planning.analyzeRequirement({ description: process.argv.slice(2).join(" ") });
  console.log(JSON.stringify(planning.data, null, 2));
}

void main();
