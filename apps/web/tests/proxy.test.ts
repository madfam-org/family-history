import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { proxy } from "@/proxy";

function request(url: string, host: string) {
  return new NextRequest(url, { headers: { host } });
}

describe("proxy", () => {
  beforeEach(() => {
    vi.stubEnv("FH_ENV", "production");
    vi.stubEnv("FH_PUBLIC_LANDING_HOST", "fh.madfam.io");
    vi.stubEnv("FH_PUBLIC_APP_HOST", "fh-app.madfam.io");
    vi.stubEnv("FH_INDEXABLE", "");
  });

  it("rewrites landing pages and marks every response noindex by default", async () => {
    const response = await proxy(request("https://fh.madfam.io/es", "fh.madfam.io"));
    expect(response.headers.get("x-middleware-rewrite")).toContain("/es/site");
    expect(response.headers.get("X-Robots-Tag")).toBe("noindex, nofollow");
    expect(response.headers.get("Content-Security-Policy")).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
    expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
  });

  it("adds X-Robots-Tag to static assets and redirects too", async () => {
    const asset = await proxy(request("https://fh.madfam.io/_next/static/a.js", "fh.madfam.io"));
    expect(asset.headers.get("X-Robots-Tag")).toBe("noindex, nofollow");
    const redirect = await proxy(request("https://fh.madfam.io/", "fh.madfam.io"));
    expect(redirect.status).toBe(307);
    expect(redirect.headers.get("Location")).toBe("https://fh.madfam.io/es");
    expect(redirect.headers.get("X-Robots-Tag")).toBe("noindex, nofollow");
  });

  it("drops the robots header on the landing only when FH_INDEXABLE is exactly true", async () => {
    vi.stubEnv("FH_INDEXABLE", "true");
    const landing = await proxy(request("https://fh.madfam.io/es", "fh.madfam.io"));
    expect(landing.headers.get("X-Robots-Tag")).toBeNull();
    const app = await proxy(request("https://fh-app.madfam.io/es", "fh-app.madfam.io"));
    expect(app.headers.get("X-Robots-Tag")).toBe("noindex, nofollow");
  });

  it("routes the app host to the app tree and 404s internal paths", async () => {
    const app = await proxy(request("https://fh-app.madfam.io/es/ajustes", "fh-app.madfam.io"));
    expect(app.headers.get("x-middleware-rewrite")).toContain("/es/workspace/ajustes");
    const internal = await proxy(request("https://fh-app.madfam.io/es/site", "fh-app.madfam.io"));
    expect(internal.status).toBe(404);
  });
});

describe("proxy second pass", () => {
  beforeEach(() => {
    vi.stubEnv("FH_ENV", "production");
    vi.stubEnv("FH_PUBLIC_LANDING_HOST", "fh.madfam.io");
    vi.stubEnv("FH_PUBLIC_APP_HOST", "fh-app.madfam.io");
  });

  it("lets its own rewrite through and refuses a forged marker", async () => {
    const first = await proxy(request("https://fh.madfam.io/es", "fh.madfam.io"));
    const marker = first.headers.get("x-middleware-request-x-fh-internal");
    expect(marker).toBeTruthy();
    const second = await proxy(
      new NextRequest("https://fh.madfam.io/es/site", { headers: { host: "fh.madfam.io", "x-fh-internal": marker ?? "" } }),
    );
    expect(second.status).toBe(200);
    expect(second.headers.get("x-middleware-next")).toBe("1");
    const forged = await proxy(
      new NextRequest("https://fh.madfam.io/es/site", { headers: { host: "fh.madfam.io", "x-fh-internal": "guess" } }),
    );
    expect(forged.status).toBe(404);
  });
});
