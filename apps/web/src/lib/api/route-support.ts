/**
 * Shared pieces for the app's route handlers under /api/app/ (job polling, uploads, downloads):
 * the signed-in API client without redirects, JSON error envelopes with the same codes the API
 * uses, and a byte limit for streamed uploads.
 */
import "server-only";

import { createApiClient, type ApiClient } from "@/lib/api/client";
import { getSession } from "@/lib/auth/server";

import { errorMessageKey, isApiError, type ErrorCode } from "./errors";

export function errorJson(code: ErrorCode, status: number): Response {
  return Response.json(
    { error: { code, message: code } },
    { status, headers: { "cache-control": "no-store" } },
  );
}

/** The signed-in API client, or a 401 envelope (route handlers never redirect). */
export async function routeApi(): Promise<ApiClient | Response> {
  const session = await getSession();
  if (!session) return errorJson("unauthorized", 401);
  return createApiClient({ accessToken: session.accessToken });
}

/** Maps a thrown error to an envelope; anything that is not an `ApiError` is rethrown. */
export function apiErrorResponse(error: unknown): Response {
  if (!isApiError(error)) throw error;
  const status = error.status >= 400 && error.status < 600 ? error.status : 502;
  return errorJson(errorMessageKey(error.code), status);
}

export class UploadTooLargeError extends Error {
  constructor() {
    super("upload exceeds the limit");
    this.name = "UploadTooLargeError";
  }
}

/** Passes bytes through until `limit`, then errors the stream (the upload is abandoned). */
export function byteLimit(limit: number): { stream: TransformStream<Uint8Array, Uint8Array>; exceeded: () => boolean } {
  let seen = 0;
  let over = false;
  const stream = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      seen += chunk.byteLength;
      if (seen > limit) {
        over = true;
        controller.error(new UploadTooLargeError());
        return;
      }
      controller.enqueue(chunk);
    },
  });
  return { stream, exceeded: () => over };
}
