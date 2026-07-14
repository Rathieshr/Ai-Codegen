export interface SdkTelemetry {
  operation: string;
  durationMs: number;
  success: boolean;
  retries: number;
  cacheHit: boolean;
  transport: string;
}

export interface ITelemetrySink { record(value: SdkTelemetry): void; }
export class NoopTelemetrySink implements ITelemetrySink { record(_value: SdkTelemetry): void {} }
export class MemoryTelemetrySink implements ITelemetrySink {
  private readonly values: SdkTelemetry[] = [];
  record(value: SdkTelemetry): void { this.values.push({ ...value }); }
  list(): SdkTelemetry[] { return this.values.map(value => ({ ...value })); }
}
