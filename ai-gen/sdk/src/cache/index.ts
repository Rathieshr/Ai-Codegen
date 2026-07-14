export interface CacheEntry<T> { value: T; versions: Record<string, string>; expiresAt: number; }

export interface ISdkCache {
  get<T>(key: string, versions?: Record<string, string>): T | undefined;
  set<T>(key: string, value: T, versions?: Record<string, string>, ttlMs?: number): void;
  invalidate(predicate?: (key: string) => boolean): number;
}

export class MemorySdkCache implements ISdkCache {
  private readonly entries = new Map<string, CacheEntry<unknown>>();
  get<T>(key: string, versions: Record<string, string> = {}): T | undefined {
    const entry = this.entries.get(key);
    if (!entry || entry.expiresAt < Date.now() || !sameVersions(entry.versions, versions)) {
      if (entry) this.entries.delete(key);
      return undefined;
    }
    return entry.value as T;
  }
  set<T>(key: string, value: T, versions: Record<string, string> = {}, ttlMs = 300000): void {
    this.entries.set(key, { value, versions: { ...versions }, expiresAt: Date.now() + ttlMs });
  }
  invalidate(predicate: (key: string) => boolean = () => true): number {
    let count = 0;
    for (const key of this.entries.keys()) if (predicate(key)) { this.entries.delete(key); count += 1; }
    return count;
  }
}

function sameVersions(left: Record<string, string>, right: Record<string, string>): boolean {
  return Object.keys({ ...left, ...right }).every(key => left[key] === right[key]);
}
