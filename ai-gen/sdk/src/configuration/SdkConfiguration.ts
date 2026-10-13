export type SdkEnvironment = "local" | "development" | "test" | "staging" | "production";
export type AuthenticationMode = "anonymous" | "apiKey" | "bearer" | "azureAd" | "pat";

export interface ProviderPreferences {
  preferredProvider?: string;
  preferredModel?: string;
  allowLocalModels?: boolean;
}

export interface SdkConfiguration {
  baseUrl: string;
  environment?: SdkEnvironment;
  timeoutMs?: number;
  retryCount?: number;
  retryDelayMs?: number;
  apiVersion?: string;
  authenticationMode?: AuthenticationMode;
  defaultRepository?: string;
  defaultProject?: string;
  enableCaching?: boolean;
  enableDiagnostics?: boolean;
  enableTelemetry?: boolean;
  providerPreferences?: ProviderPreferences;
  sdkVersion?: string;
  platformVersion?: string;
}

export interface ResolvedSdkConfiguration extends Required<Omit<SdkConfiguration,
  "defaultRepository" | "defaultProject" | "providerPreferences" | "platformVersion"
>> {
  defaultRepository?: string;
  defaultProject?: string;
  providerPreferences: ProviderPreferences;
  platformVersion?: string;
}

export function resolveConfiguration(input: SdkConfiguration): ResolvedSdkConfiguration {
  if (!input.baseUrl?.trim()) throw new Error("HEI SDK baseUrl is required.");
  return {
    ...input,
    baseUrl: input.baseUrl.replace(/\/+$/, ""),
    environment: input.environment ?? "production",
    timeoutMs: input.timeoutMs ?? 30000,
    retryCount: input.retryCount ?? 2,
    retryDelayMs: input.retryDelayMs ?? 250,
    apiVersion: input.apiVersion ?? "v1",
    authenticationMode: input.authenticationMode ?? "anonymous",
    enableCaching: input.enableCaching ?? true,
    enableDiagnostics: input.enableDiagnostics ?? true,
    enableTelemetry: input.enableTelemetry ?? false,
    providerPreferences: input.providerPreferences ?? {},
    sdkVersion: input.sdkVersion ?? "0.1.0"
  };
}
