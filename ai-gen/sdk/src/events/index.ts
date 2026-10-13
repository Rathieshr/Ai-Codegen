export type SdkEventName =
  | "RequestStarted" | "RequestCompleted" | "RequestFailed" | "Retry"
  | "AuthenticationFailed" | "ConnectionLost" | "Reconnect";

export interface SdkEvent {
  name: SdkEventName;
  operation?: string;
  correlationId?: string;
  timestamp: string;
  details?: Record<string, unknown>;
}

export type SdkEventHandler = (event: SdkEvent) => void;

export class SdkEventBus {
  private readonly handlers = new Map<SdkEventName | "*", Set<SdkEventHandler>>();
  subscribe(name: SdkEventName | "*", handler: SdkEventHandler): () => void {
    const values = this.handlers.get(name) ?? new Set<SdkEventHandler>();
    values.add(handler); this.handlers.set(name, values);
    return () => values.delete(handler);
  }
  publish(event: Omit<SdkEvent, "timestamp">): void {
    const value: SdkEvent = { ...event, timestamp: new Date().toISOString() };
    for (const key of [event.name, "*"] as const) for (const handler of this.handlers.get(key) ?? []) handler(value);
  }
}
