import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import { createPerson, getMe, listPeople } from "@/lib/api/endpoints";
import { ApiError, codeForStatus, errorMessageKey, KNOWN_ERROR_CODES } from "@/lib/api/errors";
import { load } from "@/lib/api/load";

const BASE = "http://api.internal.test";
const SPACE_ID = "6f1c1d3e-8f0a-4b8e-9d2e-1a2b3c4d5e6f";

function client(handler: (url: URL, init: RequestInit) => Response | Promise<Response>) {
  const calls: { url: URL; init: RequestInit }[] = [];
  const api = createApiClient({
    baseUrl: BASE,
    accessToken: "access-synthetic",
    fetchImpl: (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      calls.push({ url, init: init ?? {} });
      return handler(url, init ?? {});
    }) as typeof fetch,
  });
  return { api, calls };
}

describe("error-code mapping", () => {
  it("maps the early-access error to its own message key", () => {
    expect(errorMessageKey("early_access_required")).toBe("early_access_required");
  });

  it("keeps known codes, maps aliases and hides unknown ones", () => {
    for (const code of KNOWN_ERROR_CODES) expect(errorMessageKey(code)).toBe(code);
    expect(errorMessageKey("invalid_token")).toBe("unauthorized");
    expect(errorMessageKey("space_not_found")).toBe("not_found");
    expect(errorMessageKey("event_not_found")).toBe("not_found");
    expect(errorMessageKey("insufficient_scope")).toBe("forbidden");
    expect(errorMessageKey("something_new")).toBe("unknown");
  });

  it("derives a code from the HTTP status when the body has no envelope", () => {
    expect(codeForStatus(401)).toBe("unauthorized");
    expect(codeForStatus(403)).toBe("forbidden");
    expect(codeForStatus(404)).toBe("not_found");
    expect(codeForStatus(422)).toBe("validation_error");
    expect(codeForStatus(429)).toBe("rate_limited");
    expect(codeForStatus(503)).toBe("server_error");
    expect(codeForStatus(418)).toBe("unknown");
  });
});

describe("API client", () => {
  it("sends the bearer token and parses the contract shape", async () => {
    const { api, calls } = client(() =>
      Response.json({
        sub: "user-1",
        email: "ana@example.test",
        name: "Ana Prueba",
        early_access: true,
        spaces: [{ id: SPACE_ID, name: "Familia Prueba", role: "steward", people_count: 3 }],
      }),
    );
    const me = await getMe(api);
    expect(me.spaces[0]?.role).toBe("steward");
    expect(new Headers(calls[0]?.init.headers).get("authorization")).toBe("Bearer access-synthetic");
    expect(calls[0]?.url.toString()).toBe(`${BASE}/v1/me`);
  });

  it("turns the error envelope into an ApiError with the API's code", async () => {
    const { api } = client(() =>
      Response.json({ error: { code: "early_access_required", message: "Early access required" } }, { status: 403 }),
    );
    await expect(getMe(api)).rejects.toMatchObject({ status: 403, code: "early_access_required" });
    await expect(load(() => getMe(api))).resolves.toEqual({ ok: false, code: "early_access_required", status: 403 });
  });

  it("falls back to the status code when the error body is not an envelope", async () => {
    const { api } = client(() => new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(getMe(api)).rejects.toMatchObject({ status: 502, code: "server_error" });
  });

  it("reports contract drift as invalid_response", async () => {
    const { api } = client(() => Response.json({ sub: "user-1" }));
    await expect(getMe(api)).rejects.toMatchObject({ code: "invalid_response" });
  });

  it("reports network failures and missing configuration visibly", async () => {
    const { api } = client(() => {
      throw new TypeError("fetch failed");
    });
    await expect(getMe(api)).rejects.toMatchObject({ status: 0, code: "api_unreachable" });
    const unconfigured = createApiClient({}, {});
    await expect(getMe(unconfigured)).rejects.toMatchObject({ code: "api_not_configured" });
  });

  it("builds query strings and request bodies", async () => {
    const { api, calls } = client((url, init) =>
      init.method === "POST"
        ? Response.json({
            id: "p1",
            display_name: "Ana Prueba",
            sex: "F",
            living_status: "living",
            birth: null,
            death: null,
            visibility: "space",
          })
        : Response.json({ items: [], next_cursor: null }),
    );
    await listPeople(api, SPACE_ID, { q: "Ana", cursor: undefined });
    expect(calls[0]?.url.searchParams.get("q")).toBe("Ana");
    expect(calls[0]?.url.searchParams.has("cursor")).toBe(false);
    const person = await createPerson(api, SPACE_ID, {
      sex: "F",
      names: [{ given: "Ana", apellido_paterno: "Prueba", nicknames: [] }],
    });
    expect(person.names).toEqual([]);
    expect(JSON.parse(String(calls[1]?.init.body))).toEqual({
      sex: "F",
      names: [{ given: "Ana", apellido_paterno: "Prueba", nicknames: [] }],
    });
  });

  it("is an Error subclass", () => {
    expect(new ApiError(500, "server_error", "x")).toBeInstanceOf(Error);
  });
});
