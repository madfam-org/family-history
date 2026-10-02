/**
 * Import and export jobs: the client polling helpers and the route handlers that stream uploads
 * and downloads (with the API client injected).
 */
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { IMPORT_MAX_BYTES } from "@/lib/api/endpoints";
import { handleImportUpload, handleJobDownload, handleJobStatus, UPLOAD_LIMIT } from "@/lib/jobs/handlers";
import { checkImportFile, downloadHref, formatBytes, MAX_DELAY_MS, nextDelay, pollJob } from "@/lib/jobs/polling";

const SPACE = "6f1c1d3e-8f0a-4b8e-9d2e-1a2b3c4d5e6f";
const APP = "https://fh-app.example.test";
const ENV = { FH_PUBLIC_APP_HOST: "fh-app.example.test", FH_ENV: "production" };

function api(handler: (url: URL, init: RequestInit) => Response | Promise<Response>) {
  const calls: Array<{ url: URL; init: RequestInit }> = [];
  const client = createApiClient({
    baseUrl: "http://api.internal.test",
    accessToken: "access-synthetic",
    fetchImpl: (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      calls.push({ url, init: init ?? {} });
      return handler(url, init ?? {});
    }) as typeof fetch,
  });
  return { get: async () => client, calls };
}

function upload(body: BodyInit, headers: Record<string, string> = {}) {
  return new Request(`${APP}/api/app/spaces/${SPACE}/imports`, {
    method: "POST",
    body,
    headers: { origin: APP, "content-type": "multipart/form-data; boundary=x", ...headers },
    duplex: "half",
  } as RequestInit);
}

describe("polling helpers", () => {
  it("backs off from 1 s to at most 10 s", () => {
    expect(nextDelay(0)).toBe(1000);
    expect(nextDelay(1)).toBe(1500);
    expect(nextDelay(50)).toBe(MAX_DELAY_MS);
  });

  it("parses a job, retries transient failures and stops on final ones", async () => {
    const job = { id: "job-1", kind: "export", status: "running", created_at: "2026-10-01T12:00:00Z" };
    const ok = vi.fn(async (_input: RequestInfo | URL) => Response.json(job));
    expect(await pollJob("job-1", ok as unknown as typeof fetch)).toEqual({ ok: true, job });
    expect(ok.mock.calls[0]?.[0]).toBe("/api/app/jobs/job-1");

    const gone = vi.fn(async () => Response.json({ error: { code: "job_not_found", message: "x" } }, { status: 404 }));
    expect(await pollJob("job-1", gone as unknown as typeof fetch)).toEqual({ ok: false, code: "not_found", retry: false });

    const down = vi.fn(async () => {
      throw new TypeError("offline");
    });
    expect(await pollJob("job-1", down as unknown as typeof fetch)).toEqual({ ok: false, code: "api_unreachable", retry: true });

    const odd = vi.fn(async () => Response.json({ status: "weird" }));
    expect(await pollJob("job-1", odd as unknown as typeof fetch)).toMatchObject({ ok: false, code: "invalid_response" });
  });

  it("checks the file before uploading", () => {
    expect(checkImportFile(null, IMPORT_MAX_BYTES)).toBe("noFile");
    expect(checkImportFile({ name: "arbol.txt", size: 10 }, IMPORT_MAX_BYTES)).toBe("wrongType");
    expect(checkImportFile({ name: "ARBOL.GED", size: 10 }, IMPORT_MAX_BYTES)).toBeNull();
    expect(checkImportFile({ name: "family-history-2026-10-01.json", size: 10 }, IMPORT_MAX_BYTES)).toBeNull();
    expect(checkImportFile({ name: "arbol.gdz", size: IMPORT_MAX_BYTES + 1 }, IMPORT_MAX_BYTES)).toBe("tooLarge");
    expect(checkImportFile({ name: "arbol.gdz", size: IMPORT_MAX_BYTES }, IMPORT_MAX_BYTES)).toBeNull();
  });

  it("formats sizes like the limit is written", () => {
    expect(formatBytes(25 * 1024 * 1024, "es")).toBe("25 MiB");
    expect(formatBytes(1536, "en")).toBe("1.5 KiB");
  });

  it("builds a download link that returns to the export page", () => {
    expect(downloadHref("job-1", "/es/familias/x/exportar")).toBe(
      "/api/app/jobs/job-1/download?volver=%2Fes%2Ffamilias%2Fx%2Fexportar",
    );
  });
});

describe("import upload route", () => {
  it("refuses cross-site posts", async () => {
    const { get } = api(() => Response.json({ job_id: "job-1" }, { status: 202 }));
    const response = await handleImportUpload(upload("x", { origin: "https://elsewhere.example.test" }), SPACE, get, ENV);
    expect(response.status).toBe(403);
  });

  it("refuses non-multipart bodies, bad ids and declared oversize uploads", async () => {
    const { get } = api(() => Response.json({ job_id: "job-1" }, { status: 202 }));
    expect((await handleImportUpload(upload("x", { "content-type": "application/json" }), SPACE, get, ENV)).status).toBe(415);
    expect((await handleImportUpload(upload("x"), "../../etc", get, ENV)).status).toBe(404);
    const big = await handleImportUpload(upload("x", { "content-length": String(UPLOAD_LIMIT + 1) }), SPACE, get, ENV);
    expect(big.status).toBe(413);
    expect(await big.json()).toEqual({ error: { code: "file_too_large", message: "file_too_large" } });
  });

  it("streams the body to the API with its boundary and answers 202 {job_id}", async () => {
    const { get, calls } = api(async (_url, init) => {
      const text = await new Response(init.body as BodyInit).text();
      expect(text).toBe("--x\r\ncontenido\r\n--x--");
      return Response.json({ job_id: "job-7" }, { status: 202 });
    });
    const response = await handleImportUpload(upload("--x\r\ncontenido\r\n--x--"), SPACE, get, ENV);
    expect(response.status).toBe(202);
    expect(await response.json()).toEqual({ job_id: "job-7" });
    expect(calls[0]?.url.pathname).toBe(`/v1/spaces/${SPACE}/imports`);
    expect((calls[0]?.init.headers as Record<string, string>)["content-type"]).toBe("multipart/form-data; boundary=x");
  });

  it("passes the API's refusals through with the same code", async () => {
    const { get } = api(() => Response.json({ error: { code: "forbidden", message: "Editors only." } }, { status: 403 }));
    const response = await handleImportUpload(upload("--x--"), SPACE, get, ENV);
    expect(response.status).toBe(403);
    expect(await response.json()).toMatchObject({ error: { code: "forbidden" } });
  });

  it("answers 401 without a session", async () => {
    const response = await handleImportUpload(upload("--x--"), SPACE, async () => Response.json({}, { status: 401 }), ENV);
    expect(response.status).toBe(401);
  });
});

describe("job status and download routes", () => {
  it("returns the job for polling, never cached", async () => {
    const job = { id: "job-1", kind: "import", status: "succeeded", report: {}, created_at: "2026-10-01T12:00:00Z" };
    const { get } = api(() => Response.json(job));
    const response = await handleJobStatus("job-1", get);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toMatchObject({ status: "succeeded" });
    expect((await handleJobStatus("../x", get)).status).toBe(404);
  });

  it("streams the file with only safe headers", async () => {
    const { get } = api(
      () =>
        new Response("0 HEAD", {
          headers: {
            "content-type": "application/octet-stream",
            "content-disposition": 'attachment; filename="familia.gdz"',
            "set-cookie": "upstream=1",
          },
        }),
    );
    const response = await handleJobDownload(new Request(`${APP}/api/app/jobs/job-1/download`), "job-1", get);
    expect(response.status).toBe(200);
    expect(response.headers.get("content-disposition")).toBe('attachment; filename="familia.gdz"');
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(await response.text()).toBe("0 HEAD");
  });

  it("sends the browser back with download_expired after 24 hours (410)", async () => {
    const { get } = api(() => new Response("gone", { status: 410 }));
    const back = "/es/familias/x/exportar";
    const request = new Request(`${APP}/api/app/jobs/job-1/download?volver=${encodeURIComponent(back)}`);
    const response = await handleJobDownload(request, "job-1", get);
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(`${back}?trabajo=job-1&error=download_expired`);
  });

  it("never redirects outside the app", async () => {
    const { get } = api(() => new Response("gone", { status: 410 }));
    const request = new Request(`${APP}/api/app/jobs/job-1/download?volver=${encodeURIComponent("//evil.example.test/x")}`);
    const response = await handleJobDownload(request, "job-1", get);
    expect(response.headers.get("location")?.startsWith("/es?")).toBe(true);
  });
});
