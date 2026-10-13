import { RequestDiagnostics } from "../models";

export interface IDiagnosticsSink { record(value: RequestDiagnostics): void; }

export class MemoryDiagnosticsSink implements IDiagnosticsSink {
  private readonly values: RequestDiagnostics[] = [];
  record(value: RequestDiagnostics): void { this.values.push({ ...value, warnings: [...value.warnings], errors: [...value.errors], versions: { ...value.versions } }); }
  list(): RequestDiagnostics[] { return this.values.map(value => ({ ...value, warnings: [...value.warnings], errors: [...value.errors], versions: { ...value.versions } })); }
  latest(): RequestDiagnostics | undefined { return this.list().at(-1); }
}

export * from "./telemetry";
