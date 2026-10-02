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
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  query?: Record<string, string | number | undefined | null>;
  /** JSON body. */
  body?: unknown;
  /**
   * A body sent as is (a multipart upload streamed through), with its own content type. It is
   * mutually exclusive with `body`.
   */
  raw?: { stream: ReadableStream<Uint8Array>; contentType: string };
  /** Overrides the default timeout (uploads and downloads take longer). */
  timeoutMs?: number;
  accept?: string;
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
    const headers: Record<string, string> = { accept: request.accept ?? "application/json" };
    if (options.accessToken) headers.authorization = `Bearer ${options.accessToken}`;
    let body: BodyInit | undefined;
    if (request.raw) {
      headers["content-type"] = request.raw.contentType;
      body = request.raw.stream;
    } else if (request.body !== undefined) {
      headers["content-type"] = "application/json";
      body = JSON.stringify(request.body);
    }
    let response: Response;
    try {
      const init: RequestInit & { duplex?: "half" } = {
        method: request.method ?? "GET",
        headers,
        body,
        signal: AbortSignal.timeout(request.timeoutMs ?? timeoutMs),
        cache: "no-store",
      };
      // Streaming request bodies need half duplex in Node's fetch.
      if (request.raw) init.duplex = "half";
      response = await fetchImpl(url, init);
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

  /** The successful response itself, for downloads streamed through to the browser. */
  async function stream(path: string, request: RequestOptions = {}): Promise<Response> {
    return send(path, request);
  }

  return { json, empty, stream };
}

export type ApiClient = ReturnType<typeof createApiClient>;
