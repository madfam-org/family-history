import { describe, expect, it } from "vitest";

import { parseAviso, isValidAvisoVersion } from "@/lib/waitlist/aviso";
import { waitlistState } from "@/lib/waitlist/gate";
import { submitWaitlist } from "@/lib/waitlist/submit";

const open = { FH_WAITLIST_ENABLED: "true", FH_AVISO_VERSION: "2026-10", FH_API_INTERNAL_URL: "http://api.internal.test" };

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

describe("waitlist gate", () => {
  it("stays closed unless enabled AND an aviso version is set", () => {
    expect(waitlistState({})).toEqual({ open: false });
    expect(waitlistState({ FH_WAITLIST_ENABLED: "true" })).toEqual({ open: false });
    expect(waitlistState({ FH_AVISO_VERSION: "2026-10" })).toEqual({ open: false });
    expect(waitlistState({ FH_WAITLIST_ENABLED: "yes", FH_AVISO_VERSION: "2026-10" })).toEqual({ open: false });
    expect(waitlistState({ FH_WAITLIST_ENABLED: "true", FH_AVISO_VERSION: "  " })).toEqual({ open: false });
    expect(waitlistState(open)).toEqual({ open: true, avisoVersion: "2026-10" });
  });

  it("stays closed when the aviso is not published", () => {
    expect(waitlistState(open, false)).toEqual({ open: false });
  });
});

describe("waitlist submission", () => {
  const published = async () => true;

  it("posts {email, locale, consent: true, aviso_version} to the API", async () => {
    const requests: { url: string; body: unknown }[] = [];
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), body: JSON.parse(String(init?.body)) });
      return new Response(null, { status: 202 });
    }) as typeof fetch;
    const result = await submitWaitlist(form({ email: " ana@example.test ", consent: "on", locale: "en" }), {
      env: open,
      fetchImpl,
      isAvisoPublished: published,
    });
    expect(result).toEqual({ status: "success" });
    expect(requests).toEqual([
      {
        url: "http://api.internal.test/v1/waitlist",
        body: { email: "ana@example.test", locale: "en", consent: true, aviso_version: "2026-10" },
      },
    ]);
  });

  it("refuses to collect anything while the gate is closed, even on a forged post", async () => {
    const fetchImpl = (async () => {
      throw new Error("must not be called");
    }) as typeof fetch;
    const closed = await submitWaitlist(form({ email: "ana@example.test", consent: "on" }), {
      env: {},
      fetchImpl,
      isAvisoPublished: published,
    });
    expect(closed).toMatchObject({ status: "error", error: "closed" });
    const unpublished = await submitWaitlist(form({ email: "ana@example.test", consent: "on" }), {
      env: open,
      fetchImpl,
      isAvisoPublished: async () => false,
    });
    expect(unpublished).toMatchObject({ status: "error", error: "closed" });
  });

  it("requires a valid email and explicit consent", async () => {
    const fetchImpl = (async () => new Response(null, { status: 202 })) as typeof fetch;
    const deps = { env: open, fetchImpl, isAvisoPublished: published };
    await expect(submitWaitlist(form({ email: "not-an-email", consent: "on" }), deps)).resolves.toMatchObject({
      error: "invalidEmail",
    });
    await expect(submitWaitlist(form({ email: "ana@example.test" }), deps)).resolves.toMatchObject({
      error: "consentRequired",
      email: "ana@example.test",
    });
  });

  it("reports rate limiting and outages honestly", async () => {
    const limited = (async () =>
      Response.json({ error: { code: "rate_limited", message: "slow down" } }, { status: 429 })) as typeof fetch;
    await expect(
      submitWaitlist(form({ email: "ana@example.test", consent: "on" }), {
        env: open,
        fetchImpl: limited,
        isAvisoPublished: published,
      }),
    ).resolves.toMatchObject({ error: "rateLimited" });
    const down = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    await expect(
      submitWaitlist(form({ email: "ana@example.test", consent: "on" }), {
        env: open,
        fetchImpl: down,
        isAvisoPublished: published,
      }),
    ).resolves.toMatchObject({ error: "unavailable" });
  });
});

describe("aviso files", () => {
  it("accept only safe version names", () => {
    expect(isValidAvisoVersion("2026-10")).toBe(true);
    expect(isValidAvisoVersion("v1.2")).toBe(true);
    for (const bad of ["../etc/passwd", "a/b", "", ".hidden", "a..b"]) expect(isValidAvisoVersion(bad)).toBe(false);
  });

  it("parse headings and paragraphs", () => {
    expect(parseAviso("# Título\n\nPrimer párrafo\ncontinúa.\n\nSegundo.")).toEqual([
      { kind: "heading", text: "Título" },
      { kind: "paragraph", text: "Primer párrafo continúa." },
      { kind: "paragraph", text: "Segundo." },
    ]);
  });
});
