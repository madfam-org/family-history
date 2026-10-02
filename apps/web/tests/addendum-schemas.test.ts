/**
 * Every response shape of the wave-2 contract addendum, parsed with the web's zod schemas, plus
 * the endpoints that send the addendum's requests. Synthetic data only: names come from the
 * domain lexicon (api/src/family_history/domain/data/names.py).
 */
import { describe, expect, it } from "vitest";

import { createApiClient } from "@/lib/api/client";
import {
  createAssociation,
  createEvent,
  createRelationship,
  deleteAssociation,
  deleteRelationship,
  downloadJob,
  getCompadrazgo,
  getJob,
  getKinship,
  getPerson,
  patchEvent,
  startExport,
  startImport,
} from "@/lib/api/endpoints";
import { isPrivatePerson, peoplePageSchema, personSchema, personSummarySchema } from "@/lib/api/schemas";
import {
  compadrazgoSchema,
  downloadExpiresAt,
  jobAcceptedSchema,
  jobSchema,
  kinshipSchema,
  summarizeImportReport,
} from "@/lib/api/schemas-family";

const BASE = "http://api.internal.test";
const SPACE = "6f1c1d3e-8f0a-4b8e-9d2e-1a2b3c4d5e6f";
const PETRA = "0a8b5c2e-7d41-4a8e-9a0b-0c1d2e3f4a5b";
const JESUS = "1b9c6d3f-8e52-4b9f-8b1c-1d2e3f4a5b6c";
const EVENT = "2cad7e4a-9f63-4cab-9c2d-2e3f4a5b6c7d";

const brief = {
  date_value: "ABT 1890",
  date_display: { es: "hacia 1890", en: "about 1890" },
  place: null,
};

function fullPerson(overrides: Record<string, unknown> = {}) {
  return {
    id: PETRA,
    space_id: SPACE,
    display_name: "Petra Ramírez Luna",
    sort_name: "Ramírez Luna, Petra",
    sex: "F",
    living_status: "presumed_deceased",
    is_private: false,
    visibility: "space",
    names: [
      {
        id: "n-1",
        position: 0,
        given: "Petra",
        apellido_paterno: "Ramírez",
        apellido_materno: "Luna",
        extra_surnames: [],
        particles: {},
        nombre_de_pila: null,
        nombre_usado: null,
        nicknames: ["Petrita"],
        name_type: "birth",
        lang: "es-MX",
        surname_order: "paterno_materno",
        is_primary: true,
      },
    ],
    events: [
      {
        id: EVENT,
        space_id: SPACE,
        type: "baptism",
        date_value: "ABT 1890",
        date_original: "hacia 1890",
        date_display: { es: "hacia 1890", en: "about 1890" },
        date_earliest: "1885-01-01",
        date_latest: "1895-12-31",
        place_id: null,
        place: null,
        description: null,
        sensitivity: "religion",
        participants: [{ person_id: PETRA, role: "principal" }],
        created_by: "user-1",
        created_at: "2026-10-01T12:00:00Z",
        updated_at: "2026-10-01T12:00:00Z",
      },
    ],
    relationships: [],
    citations: [],
    created_by: "user-1",
    created_at: "2026-10-01T12:00:00Z",
    updated_at: "2026-10-01T12:00:00Z",
    ...overrides,
  };
}

describe("addendum A and B: people and events", () => {
  it("parses the API's full Person, which has events instead of birth/death briefs", () => {
    const parsed = personSchema.parse(fullPerson());
    expect(parsed.birth).toBeUndefined();
    expect(parsed.events[0]?.date_display).toEqual({ es: "hacia 1890", en: "about 1890" });
    expect(parsed.events[0]?.date_original).toBe("hacia 1890");
    expect(parsed.events[0]?.associations).toEqual([]);
    expect(parsed.sort_name).toBe("Ramírez Luna, Petra");
  });

  it("accepts the four living statuses and rejects anything else", () => {
    for (const status of ["living", "deceased", "presumed_deceased", "unknown"]) {
      expect(personSchema.safeParse(fullPerson({ living_status: status })).success).toBe(true);
    }
    expect(personSchema.safeParse(fullPerson({ living_status: "alive" })).success).toBe(false);
  });

  it("parses EventBrief with date_display, and defaults it to null when absent", () => {
    const page = peoplePageSchema.parse({
      items: [
        {
          id: PETRA,
          display_name: "Petra Ramírez Luna",
          sex: "F",
          living_status: "deceased",
          is_private: false,
          birth: brief,
          death: { date_value: "1961", place: null },
          visibility: "space",
        },
      ],
      next_cursor: null,
    });
    expect(page.items[0]?.birth?.date_display?.es).toBe("hacia 1890");
    expect(page.items[0]?.death?.date_display).toBeNull();
  });

  it("parses event associations when the API returns them", () => {
    const person = personSchema.parse(
      fullPerson({
        events: [
          {
            id: EVENT,
            type: "baptism",
            associations: [{ id: "a-1", person_id: JESUS, display_name: "Jesús Ortega Vega", sex: "M", role: "godparent", phrase: null }],
          },
        ],
      }),
    );
    expect(person.events[0]?.associations[0]).toMatchObject({ role: "godparent", display_name: "Jesús Ortega Vega", sex: "M" });
  });

  it("decides privacy from is_private, and errs toward private without it", () => {
    expect(isPrivatePerson({ is_private: true, living_status: "deceased" })).toBe(true);
    expect(isPrivatePerson({ is_private: false, living_status: "living" })).toBe(false);
    expect(isPrivatePerson({ living_status: "living" })).toBe(true);
    expect(isPrivatePerson({ living_status: "unknown" })).toBe(true);
    expect(isPrivatePerson({ living_status: "presumed_deceased" })).toBe(false);
    const summary = personSummarySchema.parse({
      id: PETRA,
      display_name: "Petra Ramírez Luna",
      sex: "F",
      living_status: "living",
      birth: null,
      death: null,
      visibility: "space",
    });
    expect(isPrivatePerson(summary)).toBe(true);
  });
});

describe("addendum D: kinship and compadrazgo", () => {
  it("parses a kinship answer with its structure, and refuses a bare kind", () => {
    expect(kinshipSchema.safeParse({ kinship: "blood", label_es: "tío abuelo", label_en: "great-uncle" }).success).toBe(false);
    const structured = kinshipSchema.parse({
      kinship: { kind: "blood", up: 3, down: 1, half: null, adoptive: false, partner_status: null, via: null },
      label_es: "tío abuelo",
      label_en: "great-uncle",
    });
    expect(structured.kinship.kind).toBe("blood");
    expect(kinshipSchema.safeParse({ kinship: "blood", label_es: "tío abuelo" }).success).toBe(false);
  });

  it("parses compadrazgo items", () => {
    const parsed = compadrazgoSchema.parse({
      items: [
        {
          person_id: JESUS,
          display_name: "Jesús Ortega Vega",
          relation: "padrino",
          sacrament: "bautizo",
          label_es: "padrino de bautizo",
          label_en: "baptism godfather",
        },
        { person_id: PETRA, display_name: "Petra Ramírez Luna", relation: "compadre", sacrament: "boda", label_es: "comadre de boda", label_en: "co-mother (wedding)" },
      ],
    });
    expect(parsed.items).toHaveLength(2);
  });
});

describe("addendum E: jobs", () => {
  it("parses 202 {job_id} and every job status", () => {
    expect(jobAcceptedSchema.parse({ job_id: "job-1" }).job_id).toBe("job-1");
    for (const status of ["queued", "running", "succeeded", "failed"]) {
      const job = jobSchema.parse({
        id: "job-1",
        kind: "export",
        status,
        report: null,
        error_code: status === "failed" ? "invalid_gedcom" : null,
        created_at: "2026-10-01T12:00:00Z",
        finished_at: status === "succeeded" || status === "failed" ? "2026-10-01T12:01:00Z" : null,
      });
      expect(job.status).toBe(status);
    }
    expect(jobSchema.safeParse({ id: "job-1", kind: "export", status: "done", created_at: "x" }).success).toBe(false);
  });

  it("computes the download expiry, 24 hours after the job finished", () => {
    const expires = downloadExpiresAt({ status: "succeeded", finished_at: "2026-10-01T12:00:00Z" });
    expect(expires?.toISOString()).toBe("2026-10-02T12:00:00.000Z");
    expect(downloadExpiresAt({ status: "running", finished_at: null })).toBeNull();
  });

  it("reads the import report in the GEDCOM engine's shape", () => {
    const summary = summarizeImportReport({
      source_version: "5.5.1",
      source_product: "Programa de ejemplo",
      record_counts: { INDI: 12, FAM: 4 },
      created_records: { INDI: 12 },
      diagnostics: [{ severity: "warning", code: "dual_year", message: "Dual year converted", line: 41 }],
      extension_tags: { _MILT: 2, _FH_SENSITIVITY: 3 },
    });
    expect(summary?.counts).toEqual([
      ["FAM", 4],
      ["INDI", 12],
    ]);
    expect(summary?.diagnostics[0]?.line).toBe(41);
    expect(summary?.extensions).toEqual([["_MILT", 2]]);
  });

  it("reads the alternative report keys and tolerates unknown severities", () => {
    const summary = summarizeImportReport({ counts: { INDI: 1 }, warnings: [{ severity: "notice", code: "x" }], extensions: {} });
    expect(summary?.counts).toEqual([["INDI", 1]]);
    expect(summary?.diagnostics[0]?.severity).toBe("warning");
    expect(summarizeImportReport("not a report")).toBeNull();
  });
});

function recorder(response: (url: URL, init: RequestInit) => Response) {
  const calls: Array<{ url: URL; init: RequestInit & { duplex?: string } }> = [];
  const api = createApiClient({
    baseUrl: BASE,
    accessToken: "access-synthetic",
    fetchImpl: (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      calls.push({ url, init: init ?? {} });
      return response(url, init ?? {});
    }) as typeof fetch,
  });
  return { api, calls };
}

describe("addendum endpoints", () => {
  it("asks for kinship with ?to= and for compadrazgo", async () => {
    const { api, calls } = recorder((url) =>
      url.pathname.endsWith("/kinship")
        ? Response.json({
            kinship: { kind: "in_law", up: 0, down: 0, half: null, adoptive: false, partner_status: null, via: PETRA },
            label_es: "concuño",
            label_en: "co-brother-in-law",
          })
        : Response.json({ items: [] }),
    );
    expect((await getKinship(api, PETRA, JESUS)).label_es).toBe("concuño");
    expect(calls[0]?.url.pathname).toBe(`/v1/people/${PETRA}/kinship`);
    expect(calls[0]?.url.searchParams.get("to")).toBe(JESUS);
    await getCompadrazgo(api, PETRA);
    expect(calls[1]?.url.pathname).toBe(`/v1/people/${PETRA}/compadrazgo`);
  });

  it("surfaces 404 no_relation as its own code", async () => {
    const { api } = recorder(() => Response.json({ error: { code: "no_relation", message: "No relation." } }, { status: 404 }));
    await expect(getKinship(api, PETRA, JESUS)).rejects.toMatchObject({ code: "no_relation", status: 404 });
  });

  it("sends date_original on events and surfaces 422 ambiguous_date", async () => {
    const { api, calls } = recorder((url, init) =>
      init.method === "PATCH"
        ? Response.json({ error: { code: "ambiguous_date", message: "Ambiguous." } }, { status: 422 })
        : Response.json({ id: EVENT, type: "birth", date_original: "hacia 1890" }, { status: 201 }),
    );
    await createEvent(api, SPACE, {
      type: "birth",
      date_original: "hacia 1890",
      participants: [{ person_id: PETRA, role: "principal" }],
    });
    expect(JSON.parse(String(calls[0]?.init.body))).toMatchObject({ date_original: "hacia 1890" });
    await expect(patchEvent(api, EVENT, { date_original: "1890-1895" })).rejects.toMatchObject({ code: "ambiguous_date" });
    expect(calls[1]?.url.pathname).toBe(`/v1/events/${EVENT}`);
  });

  it("creates and deletes relationships and associations", async () => {
    const { api, calls } = recorder((url, init) => {
      if (init.method === "DELETE") return new Response(null, { status: 204 });
      if (url.pathname.endsWith("/associations")) return Response.json({ id: "a-1" }, { status: 201 });
      return Response.json(
        { id: "r-1", type: "parent_child", from_person_id: JESUS, to_person_id: PETRA, qualifier: "adopted" },
        { status: 201 },
      );
    });
    await createRelationship(api, SPACE, { type: "parent_child", from_person_id: JESUS, to_person_id: PETRA, qualifier: "adopted" });
    await createAssociation(api, SPACE, { event_id: EVENT, person_id: JESUS, role: "godparent" });
    await deleteRelationship(api, "r-1");
    await deleteAssociation(api, "a-1");
    expect(calls.map((call) => `${call.init.method} ${call.url.pathname}`)).toEqual([
      `POST /v1/spaces/${SPACE}/relationships`,
      `POST /v1/spaces/${SPACE}/associations`,
      "DELETE /v1/relationships/r-1",
      "DELETE /v1/associations/a-1",
    ]);
    expect(JSON.parse(String(calls[1]?.init.body))).toEqual({ event_id: EVENT, person_id: JESUS, role: "godparent" });
  });

  it("starts exports and imports, polls jobs and streams downloads", async () => {
    const { api, calls } = recorder((url) => {
      if (url.pathname.endsWith("/download")) return new Response("0 HEAD\n", { headers: { "content-type": "text/plain" } });
      if (url.pathname.startsWith("/v1/jobs/")) {
        return Response.json({ id: "job-1", kind: "import", status: "running", created_at: "2026-10-01T12:00:00Z" });
      }
      return Response.json({ job_id: "job-1" }, { status: 202 });
    });
    expect((await startExport(api, SPACE, "gedzip")).job_id).toBe("job-1");
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ format: "gedzip" });
    const stream = new Blob(["--b\r\n"]).stream();
    await startImport(api, SPACE, { stream, contentType: "multipart/form-data; boundary=b" });
    expect(calls[1]?.init.duplex).toBe("half");
    expect((calls[1]?.init.headers as Record<string, string>)["content-type"]).toBe("multipart/form-data; boundary=b");
    expect((await getJob(api, "job-1")).status).toBe("running");
    const download = await downloadJob(api, "job-1");
    expect(await download.text()).toBe("0 HEAD\n");
  });

  it("maps a 410 on download to download_expired", async () => {
    const { api } = recorder(() => new Response("gone", { status: 410 }));
    await expect(downloadJob(api, "job-1")).rejects.toMatchObject({ code: "download_expired", status: 410 });
  });

  it("gets the full person without birth/death briefs", async () => {
    const { api } = recorder(() => Response.json(fullPerson()));
    expect((await getPerson(api, PETRA)).display_name).toBe("Petra Ramírez Luna");
  });
});
