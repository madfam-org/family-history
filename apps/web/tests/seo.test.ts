import { describe, expect, it } from "vitest";

import { buildLlmsTxt } from "@/lib/seo/llms";
import { buildRobots, R40_AGENTS } from "@/lib/seo/robots";

describe("robots", () => {
  it("disallows everything on working hosts", () => {
    expect(buildRobots({ indexable: false, surface: "landing", landingOrigin: "https://fh.madfam.io" })).toEqual({
      rules: [{ userAgent: "*", disallow: "/" }],
    });
  });

  it("disallows everything on the app host, indexable or not", () => {
    expect(buildRobots({ indexable: true, surface: "app", landingOrigin: "https://fh.madfam.io" }).rules).toEqual([
      { userAgent: "*", disallow: "/" },
    ]);
  });

  it("follows ruling R40 when indexable", () => {
    const robots = buildRobots({ indexable: true, surface: "landing", landingOrigin: "https://brand.example" });
    const rules = Array.isArray(robots.rules) ? robots.rules : [robots.rules];
    const ai = rules[0];
    expect(ai?.userAgent).toEqual([...R40_AGENTS]);
    expect(R40_AGENTS).toEqual([
      "ClaudeBot",
      "anthropic-ai",
      "GPTBot",
      "OAI-SearchBot",
      "ChatGPT-User",
      "PerplexityBot",
      "Google-Extended",
      "CCBot",
      "Applebot-Extended",
    ]);
    expect(ai?.allow).toEqual(expect.arrayContaining(["/es", "/en", "/llms.txt"]));
    expect(ai?.disallow).toEqual(expect.arrayContaining(["/auth/", "/api/"]));
    expect(robots.sitemap).toBe("https://brand.example/sitemap.xml");
  });
});

describe("llms.txt", () => {
  it("states product facts without prices and links the landing", () => {
    const text = buildLlmsTxt("https://fh.madfam.io");
    expect(text).toContain("AGPL-3.0-only");
    expect(text).toContain("https://fh.madfam.io/es");
    expect(text).toMatch(/early access/i);
    expect(text).not.toMatch(/\$\s?\d|MXN|USD/);
  });
});
