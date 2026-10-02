/**
 * The app's job route handlers (addendum E), with the API client injected so they are tested
 * without Next.js:
 *
 * - POST /api/app/spaces/<id>/imports streams the browser's multipart upload straight to the
 *   API (never buffered whole), after a same-origin check and a 25 MiB limit.
 * - GET /api/app/jobs/<id> returns the job for polling.
 * - GET /api/app/jobs/<id>/download streams the finished file; on any failure it sends the
 *   browser back to the page it came from with the error code, so a 410 after 24 hours reads as
 *   «El enlace de descarga ya venció», not as a blank error page.
 */
import "server-only";

import type { ApiClient } from "@/lib/api/client";
import { downloadJob, getJob, IMPORT_MAX_BYTES, startImport } from "@/lib/api/endpoints";
import { errorMessageKey, isApiError } from "@/lib/api/errors";
import { apiErrorResponse, byteLimit, errorJson } from "@/lib/api/route-support";
import { isSameOriginPost } from "@/lib/auth/handlers";
import { safeReturnTo } from "@/lib/auth/transaction";
import type { Env } from "@/lib/env";
import { asId } from "@/lib/forms/family";

/** Room for the multipart envelope around the file itself. */
export const MULTIPART_OVERHEAD = 64 * 1024;
export const UPLOAD_LIMIT = IMPORT_MAX_BYTES + MULTIPART_OVERHEAD;

type ApiOrResponse = ApiClient | Response;

export async function handleImportUpload(
  request: Request,
  rawSpaceId: string,
  api: () => Promise<ApiOrResponse>,
  env: Env = process.env,
): Promise<Response> {
  if (!isSameOriginPost(request, env)) return errorJson("forbidden", 403);
  const spaceId = asId(rawSpaceId);
  if (!spaceId) return errorJson("not_found", 404);
  const contentType = request.headers.get("content-type") ?? "";
  if (!contentType.toLowerCase().startsWith("multipart/form-data")) return errorJson("unsupported_file", 415);
  const declared = Number(request.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > UPLOAD_LIMIT) return errorJson("file_too_large", 413);
  if (!request.body) return errorJson("validation_error", 400);

  const client = await api();
  if (client instanceof Response) return client;
  const limit = byteLimit(UPLOAD_LIMIT);
  try {
    const accepted = await startImport(client, spaceId, {
      stream: request.body.pipeThrough(limit.stream),
      contentType,
    });
    return Response.json(accepted, { status: 202, headers: { "cache-control": "no-store" } });
  } catch (error) {
    if (limit.exceeded()) return errorJson("file_too_large", 413);
    return apiErrorResponse(error);
  }
}

export async function handleJobStatus(rawJobId: string, api: () => Promise<ApiOrResponse>): Promise<Response> {
  const jobId = rawJobId.trim();
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(jobId)) return errorJson("not_found", 404);
  const client = await api();
  if (client instanceof Response) return client;
  try {
    return Response.json(await getJob(client, jobId), { headers: { "cache-control": "no-store" } });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

const PASSED_HEADERS = ["content-type", "content-length", "content-disposition"] as const;

export async function handleJobDownload(
  request: Request,
  rawJobId: string,
  api: () => Promise<ApiOrResponse>,
): Promise<Response> {
  const url = new URL(request.url);
  const back = safeReturnTo(url.searchParams.get("volver"));
  const jobId = rawJobId.trim();
  const fail = (code: string) => {
    const target = new URLSearchParams({ trabajo: jobId, error: code });
    return new Response(null, { status: 303, headers: { location: `${back}?${target.toString()}`, "cache-control": "no-store" } });
  };
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(jobId)) return fail("not_found");
  const client = await api();
  if (client instanceof Response) return fail("unauthorized");
  try {
    const upstream = await downloadJob(client, jobId);
    const headers = new Headers({ "cache-control": "private, no-store", "x-content-type-options": "nosniff" });
    for (const name of PASSED_HEADERS) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    if (!headers.has("content-disposition")) headers.set("content-disposition", "attachment");
    return new Response(upstream.body, { status: 200, headers });
  } catch (error) {
    if (!isApiError(error)) throw error;
    return fail(errorMessageKey(error.code));
  }
}
