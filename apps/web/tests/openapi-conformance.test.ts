/**
 * Conformance with the API's final OpenAPI contract (family-history#17).
 *
 * - Every response the web parses: example payloads are generated from the component schemas
 *   (all fields, required-only with nulls, and one variant per enum value) and must pass the
 *   web's zod schemas.
 * - Every request body the web builds must validate against the API's input schemas, which
 *   reject unknown fields.
 * - The vendored copy of the components (`fixtures/openapi-v1-web.json`) must equal
 *   `packages/contracts/openapi.json` once that file holds the #17 contract, so drift fails CI.
 */
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";
import type { z } from "zod";

import fixture from "./fixtures/openapi-v1-web.json";
import { longestEnum, sample, validate, type Components, type JsonSchema } from "./support/openapi";

import {
  errorEnvelopeSchema,
  livingStatusSchema,
  meSchema,
  peoplePageSchema,
  personEventSchema,
  personSchema,
  relationshipSchema,
  roleSchema,
  sexSchema,
  spaceSchema,
  spaceSummarySchema,
  visibilitySchema,
} from "@/lib/api/schemas";
import {
  compadrazgoSchema,
  createdAssociationSchema,
  EXPORT_FORMATS,
  JOB_STATUSES,
  jobAcceptedSchema,
  jobSchema,
  kinshipSchema,
} from "@/lib/api/schemas-family";
import { ASSOCIATION_ROLES, EDITABLE_EVENT_TYPES, eventCreateBody, relationshipFor, RELATIVE_KINDS } from "@/lib/forms/family";
import { replacePrimaryName, toNameFormBody } from "@/lib/forms/names";
import { toPersonCreateBody } from "@/lib/forms/person";
import type { NameForm } from "@/lib/api/schemas";

const components = fixture.components.schemas as unknown as Components;
const ref = (name: string): JsonSchema => ({ $ref: `#/components/schemas/${name}` });

const RESPONSES: Array<[string, string, z.ZodType]> = [
  ["GET /v1/me", "Me", meSchema],
  ["GET /v1/spaces (items)", "SpaceSummary", spaceSummarySchema],
  ["POST /v1/spaces", "Space", spaceSchema],
  ["GET /v1/spaces/{id}/people", "PersonPage", peoplePageSchema],
  ["GET|POST|PATCH person", "Person", personSchema],
  ["POST|PATCH event", "Event", personEventSchema],
  ["POST relationship", "Relationship", relationshipSchema],
  ["GET kinship", "KinshipOut", kinshipSchema],
  ["GET compadrazgo", "CompadrazgoList", compadrazgoSchema],
  ["POST association", "Association", createdAssociationSchema],
  ["POST imports|exports (202)", "JobAccepted", jobAcceptedSchema],
  ["GET /v1/jobs/{id}", "Job", jobSchema],
  ["error envelope", "ErrorEnvelope", errorEnvelopeSchema],
];

describe("responses the web parses", () => {
  for (const [endpoint, component, schema] of RESPONSES) {
    it(`${endpoint} (${component})`, () => {
      const variants = Math.max(1, longestEnum(ref(component), components));
      const payloads = [
        sample(ref(component), components, { mode: "minimal", pick: 0 }),
        ...Array.from({ length: variants }, (_, pick) => sample(ref(component), components, { mode: "full", pick })),
      ];
      for (const payload of payloads) {
        const parsed = schema.safeParse(payload);
        expect(parsed.success, `${component}: ${JSON.stringify(parsed.error?.issues ?? [])}`).toBe(true);
      }
    });
  }

  it("uses exactly the API's enums where the web enumerates them", () => {
    const values = (name: string) => (components[name]?.enum ?? []) as string[];
    expect([...livingStatusSchema.options].sort()).toEqual([...values("LivingStatus")].sort());
    expect([...sexSchema.options].sort()).toEqual([...values("Sex")].sort());
    expect([...roleSchema.options].sort()).toEqual([...values("Role")].sort());
    expect([...visibilitySchema.options].sort()).toEqual([...values("Visibility")].sort());
    expect([...JOB_STATUSES].sort()).toEqual([...values("JobStatus")].sort());
    expect([...EXPORT_FORMATS].sort()).toEqual([...values("ExportFormat")].sort());
    expect([...ASSOCIATION_ROLES].sort()).toEqual([...values("AssociationRole")].sort());
    for (const type of EDITABLE_EVENT_TYPES) expect(values("EventType"), type).toContain(type);
  });
});

const P1 = "0a8b5c2e-7d41-4a8e-9a0b-0c1d2e3f4a5b";
const P2 = "1b9c6d3f-8e52-4b9f-8b1c-1d2e3f4a5b6c";
const EVENT = "2cad7e4a-9f63-4cab-9c2d-2e3f4a5b6c7d";

function expectValid(body: unknown, component: string) {
  expect(validate(body, ref(component), components)).toEqual([]);
}

describe("request bodies the web sends", () => {
  it("PersonCreate from «Agregar persona» and inline relatives", () => {
    const parsed = toPersonCreateBody({ given: "Petra", paternal: "Ramírez", maternal: "Luna", nickname: "Petrita", sex: "F", birthDate: "" });
    expect(parsed.ok).toBe(true);
    if (parsed.ok) expectValid(parsed.body, "PersonCreate");
  });

  it("PersonPatch from the name editor, keeping the other name forms", () => {
    const edited = toNameFormBody({
      given: "Ignacio",
      paternal: "Garza",
      maternal: "Treviño",
      particlePaternal: "de la",
      particleMaternal: "",
      nombreUsado: "Nacho",
      nicknames: "Chucho",
      surnameOrder: "materno_paterno",
      sex: "M",
    });
    expect(edited.ok).toBe(true);
    if (!edited.ok) return;
    const other = sample(ref("NameFormOut"), components, { mode: "full", pick: 0 }) as NameForm;
    const primary = { ...other, is_primary: true };
    expectValid({ sex: "M", names: replacePrimaryName([primary, { ...other, is_primary: false }], edited.name) }, "PersonPatch");
  });

  it("EventCreate for every editable type, with the spouse on marriages", () => {
    for (const type of EDITABLE_EVENT_TYPES) {
      expectValid(eventCreateBody({ type, personId: P1, date: "hacia 1890", description: "Parroquia de Ejemplo", spouseId: P2 }), "EventCreate");
    }
    expectValid(eventCreateBody({ type: "birth", personId: P1, date: "", description: "", spouseId: null }), "EventCreate");
  });

  it("EventPatch from «Corregir fecha»", () => {
    expectValid({ date_original: "15 de marzo de 1923" }, "EventPatch");
  });

  it("RelationshipCreate for every relative kind", () => {
    for (const kind of RELATIVE_KINDS) {
      expectValid(relationshipFor(kind, P1, P2, { pedigree: "adopted", status: "union_libre" }), "RelationshipCreate");
    }
  });

  it("AssociationCreate for each role", () => {
    expectValid({ event_id: EVENT, person_id: P2, role: "godparent" }, "AssociationCreate");
    expectValid({ event_id: EVENT, person_id: P2, role: "other", phrase: "madrina de lazo" }, "AssociationCreate");
  });

  it("ExportRequest for the four formats", () => {
    for (const format of EXPORT_FORMATS) expectValid({ format }, "ExportRequest");
  });

  it("the validator itself rejects unknown fields and bad enums", () => {
    expect(validate({ format: "pdf" }, ref("ExportRequest"), components)).not.toEqual([]);
    expect(validate({ format: "gedzip", extra: 1 }, ref("ExportRequest"), components)).not.toEqual([]);
  });
});

describe("the vendored contract", () => {
  const specPath = fileURLToPath(new URL("../../../packages/contracts/openapi.json", import.meta.url));
  const repo = existsSync(specPath)
    ? (JSON.parse(readFileSync(specPath, "utf8")) as { components: { schemas: Components } }).components.schemas
    : {};
  // `KinshipOut` arrives with #17; before it merges, main's spec predates the addendum.
  const hasFinalContract = "KinshipOut" in repo;

  it.skipIf(!hasFinalContract)("matches packages/contracts/openapi.json", () => {
    for (const [name, schema] of Object.entries(components)) expect(repo[name], name).toEqual(schema);
  });

  it("covers every component it references", () => {
    const missing = new Set<string>();
    const walk = (node: unknown) => {
      if (Array.isArray(node)) node.forEach(walk);
      else if (node && typeof node === "object") {
        const target = (node as JsonSchema).$ref?.split("/").pop();
        if (target && !(target in components)) missing.add(target);
        Object.values(node).forEach(walk);
      }
    };
    walk(components);
    expect([...missing]).toEqual([]);
  });
});
