import { NetworkException, TimeoutException } from "../core/errors";
import { ITransport, TransportRequest, TransportResponse } from "./ITransport";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export class RestTransport implements ITransport {
  readonly name = "rest";
  constructor(private readonly baseUrl: string, private readonly fetcher: FetchLike = fetch) {}

  async send<T>(request: TransportRequest): Promise<TransportResponse<T>> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), request.timeoutMs);
    try {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(request.query ?? {})) if (value !== undefined) query.set(key, String(value));
      const suffix = query.size ? `?${query}` : "";
      const response = await this.fetcher(`${this.baseUrl}${request.path}${suffix}`, {
        method: request.method,
        headers: request.headers,
        body: request.body === undefined ? undefined : JSON.stringify(request.body),
        signal: controller.signal
      });
      const text = await response.text();
      const data = text ? parsePayload(text) : undefined;
      if (!response.ok) throw new NetworkException(`HEI operation ${request.operation} failed with status ${response.status}.`, request.correlationId, response.status, data);
      const headers: Record<string, string> = {};
      response.headers.forEach((value, key) => { headers[key] = value; });
      return { data: data as T, status: response.status, headers };
    } catch (error) {
      if ((error as Error).name === "AbortError") throw new TimeoutException(`HEI operation ${request.operation} timed out.`, request.correlationId);
      if (error instanceof NetworkException) throw error;
      throw new NetworkException(`HEI operation ${request.operation} could not reach the platform.`, request.correlationId, undefined, error);
    } finally { clearTimeout(timer); }
  }
}

function parsePayload(value: string): unknown {
  try { return JSON.parse(value); } catch { return value; }
}
