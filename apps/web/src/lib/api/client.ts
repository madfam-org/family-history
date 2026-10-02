/**
 * Typed server-side client for the family-history API. Every call goes to FH_API_INTERNAL_URL
 * with the signed-in user's access token, and every response is validated with zod. Failures
 * surface as ApiError with a snake_case code (see errors.ts); nothing fails silently.
 */
import type { z } from "zod";

import { apiInternalUrl, type Env } from "@/lib/env";

import { ApiError, codeForStatus } from "./errors";
import { errorEnvelopeSchema } from "./schemas";

export type FetchLike = typeof fetch;

export interface ApiClientOptions {
  baseUrl?: string | undefined;
  accessToken?: string | undefined;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH";
  query?: Record<string, string | number | undefined | null>;
  body?: unknown;
}

const DEFAULT_TIMEOUT_MS = 15_000;

export function createApiClient(options: ApiClientOptions = {}, env: Env = process.env) {
  const baseUrl = options.baseUrl ?? apiInternalUrl(env);
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function send(path: string, request: RequestOptions): Promise<Response> {
    if (!baseUrl) throw new ApiError(0, "api_not_configured", "FH_API_INTERNAL_URL is not set");
    const url = new URL(`${baseUrl}${path}`);
    for (const [key, value] of Object.entries(request.query ?? {})) {
      if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    }
    const headers: Record<string, string> = { accept: "application/json" };
    if (options.accessToken) headers.authorization = `Bearer ${options.accessToken}`;
    if (request.body !== undefined) headers["content-type"] = "application/json";
    let response: Response;
    try {
      response = await fetchImpl(url, {
        method: request.method ?? "GET",
        headers,
        body: request.body === undefined ? undefined : JSON.stringify(request.body),
        signal: AbortSignal.timeout(timeoutMs),
        cache: "no-store",
      });
    } catch {
      throw new ApiError(0, "api_unreachable", `request to ${path} failed before a response`);
    }
    if (!response.ok) {
      const payload: unknown = await response.json().catch(() => null);
      const envelope = errorEnvelopeSchema.safeParse(payload);
      if (envelope.success) {
        throw new ApiError(response.status, envelope.data.error.code, envelope.data.error.message);
      }
      throw new ApiError(response.status, codeForStatus(response.status), `HTTP ${response.status} from ${path}`);
    }
    return response;
  }

  async function json<S extends z.ZodType>(path: string, schema: S, request: RequestOptions = {}): Promise<z.infer<S>> {
    const response = await send(path, request);
    const payload: unknown = await response.json().catch(() => undefined);
    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      throw new ApiError(response.status, "invalid_response", `response from ${path} does not match the contract`);
    }
    return parsed.data;
  }

  async function empty(path: string, request: RequestOptions = {}): Promise<number> {
    const response = await send(path, request);
    return response.status;
  }

  return { json, empty };
}

export type ApiClient = ReturnType<typeof createApiClient>;
