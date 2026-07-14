export interface TransportRequest {
  operation: string;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  headers: Record<string, string>;
  query?: Record<string, string | number | boolean | undefined>;
  body?: unknown;
  timeoutMs: number;
  correlationId: string;
}

export interface TransportResponse<T> { data: T; status: number; headers: Record<string, string>; }

export interface ITransport {
  readonly name: string;
  send<T>(request: TransportRequest): Promise<TransportResponse<T>>;
}

export interface IStreamingTransport extends ITransport {
  stream<T>(request: TransportRequest): AsyncIterable<T>;
}
