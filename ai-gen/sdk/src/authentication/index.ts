import { AuthenticationException } from "../core/errors";

export interface IAuthenticationProvider {
  readonly mode: string;
  getHeaders(): Promise<Record<string, string>>;
}

export class AnonymousAuthenticationProvider implements IAuthenticationProvider {
  readonly mode = "anonymous";
  async getHeaders(): Promise<Record<string, string>> { return {}; }
}

export class ApiKeyAuthenticationProvider implements IAuthenticationProvider {
  readonly mode = "apiKey";
  constructor(private readonly apiKey: string, private readonly headerName = "X-API-Key") {
    if (!apiKey) throw new AuthenticationException("API key is required.");
  }
  async getHeaders(): Promise<Record<string, string>> { return { [this.headerName]: this.apiKey }; }
}

export class BearerTokenAuthenticationProvider implements IAuthenticationProvider {
  readonly mode = "bearer";
  constructor(private readonly token: string | (() => Promise<string>)) {}
  async getHeaders(): Promise<Record<string, string>> {
    const value = typeof this.token === "function" ? await this.token() : this.token;
    if (!value) throw new AuthenticationException("Bearer token is unavailable.");
    return { Authorization: `Bearer ${value}` };
  }
}

export interface FutureAuthenticationProvider extends IAuthenticationProvider {
  readonly mode: "azureAd" | "pat";
}
