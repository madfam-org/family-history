import { describe, expect, it } from "vitest";

import { resolveRoute, robotsHeader, surfaceForHost } from "@/lib/routing/host-routing";

const env = {
  FH_ENV: "production",
  FH_PUBLIC_LANDING_HOST: "fh.madfam.io",
  FH_PUBLIC_APP_HOST: "fh-app.madfam.io",
};

describe("surfaceForHost", () => {
  it("maps the app host to the app and everything else to the landing", () => {
    expect(surfaceForHost("fh-app.madfam.io", env)).toBe("app");
    expect(surfaceForHost("FH-APP.madfam.io.", env)).toBe("app");
    expect(surfaceForHost("fh.madfam.io", env)).toBe("landing");
    expect(surfaceForHost("unknown.example", env)).toBe("landing");
    expect(surfaceForHost(null, env)).toBe("landing");
  });

  it("keeps ports significant for local hosts", () => {
    const local = { FH_PUBLIC_LANDING_HOST: "localhost:3000", FH_PUBLIC_APP_HOST: "app.localhost:3000" };
    expect(surfaceForHost("app.localhost:3000", local)).toBe("app");
    expect(surfaceForHost("app.localhost:4000", local)).toBe("landing");
  });
});

describe("resolveRoute on the landing host", () => {
  const route = (pathname: string, search = "") => resolveRoute({ host: "fh.madfam.io", pathname, search }, env);

  it("redirects / to the Spanish default", () => {
    expect(route("/")).toEqual({ type: "redirect", surface: "landing", location: "/es" });
  });

  it("rewrites /es and /en to the landing tree", () => {
    expect(route("/es")).toMatchObject({ type: "rewrite", locale: "es", pathname: "/es/site" });
    expect(route("/en")).toMatchObject({ type: "rewrite", locale: "en", pathname: "/en/site" });
    expect(route("/es/aviso-de-privacidad")).toMatchObject({ pathname: "/es/site/aviso-de-privacidad" });
  });

  it("prefixes unlocalised paths with /es and keeps the query", () => {
    expect(route("/aviso-de-privacidad", "?a=1")).toEqual({
      type: "redirect",
      surface: "landing",
      location: "/es/aviso-de-privacidad?a=1",
    });
  });

  it("never exposes the internal route trees", () => {
    expect(route("/es/site").type).toBe("not_found");
    expect(route("/es/workspace/ajustes").type).toBe("not_found");
  });

  it("does not serve auth routes on the landing host", () => {
    expect(route("/auth/start").type).toBe("not_found");
    expect(route("/auth/callback").type).toBe("not_found");
  });

  it("passes shared routes through on every host", () => {
    for (const path of ["/api/health", "/robots.txt", "/sitemap.xml", "/llms.txt", "/og.png"]) {
      expect(route(path).type).toBe("pass");
    }
    expect(route("/_next/static/chunk.js").type).toBe("asset");
  });
});

describe("resolveRoute on the app host", () => {
  const route = (pathname: string) => resolveRoute({ host: "fh-app.madfam.io", pathname }, env);

  it("rewrites localised paths to the app tree", () => {
    expect(route("/es")).toMatchObject({ type: "rewrite", surface: "app", pathname: "/es/workspace" });
    expect(route("/en/familias/abc")).toMatchObject({ pathname: "/en/workspace/familias/abc", locale: "en" });
  });

  it("serves the auth routes", () => {
    expect(route("/auth/start").type).toBe("pass");
    expect(route("/auth/callback").type).toBe("pass");
    expect(route("/auth/signout").type).toBe("pass");
  });

  it("redirects the bare host to /es", () => {
    expect(route("/")).toMatchObject({ type: "redirect", location: "/es" });
  });
});

describe("unknown hosts", () => {
  it("are served the landing", () => {
    expect(resolveRoute({ host: "203.0.113.7:3000", pathname: "/es" }, env)).toMatchObject({
      surface: "landing",
      pathname: "/es/site",
    });
  });
});

describe("robotsHeader", () => {
  it("is noindex everywhere unless FH_INDEXABLE is exactly true", () => {
    expect(robotsHeader("landing", env)).toBe("noindex, nofollow");
    expect(robotsHeader("landing", { ...env, FH_INDEXABLE: "TRUE" })).toBe("noindex, nofollow");
    expect(robotsHeader("landing", { ...env, FH_INDEXABLE: "1" })).toBe("noindex, nofollow");
    expect(robotsHeader("landing", { ...env, FH_INDEXABLE: "true" })).toBeUndefined();
  });

  it("keeps the app host noindex even when indexable", () => {
    expect(robotsHeader("app", { ...env, FH_INDEXABLE: "true" })).toBe("noindex, nofollow");
  });
});
