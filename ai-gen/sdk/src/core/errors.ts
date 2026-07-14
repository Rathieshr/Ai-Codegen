export type HEIErrorCode =
  | "validation" | "repository" | "planning" | "runtime" | "authentication"
  | "network" | "timeout" | "compatibility" | "unknown";

export class HEIException extends Error {
  constructor(
    message: string,
    public readonly code: HEIErrorCode = "unknown",
    public readonly correlationId?: string,
    public readonly status?: number,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = new.target.name;
  }
}

export class ValidationException extends HEIException { constructor(message: string, correlationId?: string, details?: unknown) { super(message, "validation", correlationId, 400, details); } }
export class RepositoryException extends HEIException { constructor(message: string, correlationId?: string, status?: number, details?: unknown) { super(message, "repository", correlationId, status, details); } }
export class PlanningException extends HEIException { constructor(message: string, correlationId?: string, status?: number, details?: unknown) { super(message, "planning", correlationId, status, details); } }
export class RuntimeException extends HEIException { constructor(message: string, correlationId?: string, status?: number, details?: unknown) { super(message, "runtime", correlationId, status, details); } }
export class AuthenticationException extends HEIException { constructor(message: string, correlationId?: string, status = 401, details?: unknown) { super(message, "authentication", correlationId, status, details); } }
export class NetworkException extends HEIException { constructor(message: string, correlationId?: string, status?: number, details?: unknown) { super(message, "network", correlationId, status, details); } }
export class TimeoutException extends HEIException { constructor(message: string, correlationId?: string) { super(message, "timeout", correlationId, 408); } }
export class VersionCompatibilityException extends HEIException { constructor(message: string, details?: unknown) { super(message, "compatibility", undefined, 426, details); } }
