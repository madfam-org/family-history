import { describe, expect, it } from "vitest";

import { readPersonForm, toPersonCreateBody } from "@/lib/forms/person";
import { parseSpaceForm } from "@/lib/forms/space";
import { eventTypeKey, formatName, relationshipTypeKey } from "@/lib/people/labels";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

describe("Agregar persona", () => {
  it("maps the Mexican name model and keeps the birth date as written", () => {
    const values = readPersonForm(
      form({
        given: " María  Guadalupe ",
        paternal: "Prueba",
        maternal: "Ejemplo",
        nickname: "Lupita",
        sex: "F",
        birthDate: "hacia 1931",
      }),
    );
    expect(toPersonCreateBody(values)).toEqual({
      ok: true,
      body: {
        names: [{ given: "María Guadalupe", surname_paternal: "Prueba", surname_maternal: "Ejemplo", nicknames: ["Lupita"] }],
        sex: "F",
        birth: { date_original: "hacia 1931" },
      },
    });
  });

  it("needs at least one name part and defaults sex to U", () => {
    const values = readPersonForm(form({ nickname: "Lupita", sex: "Z" }));
    expect(values.sex).toBe("U");
    expect(toPersonCreateBody(values)).toEqual({ ok: false, error: "nameRequired" });
    expect(toPersonCreateBody(readPersonForm(form({ maternal: "Ejemplo" })))).toMatchObject({
      ok: true,
      body: { birth: null, names: [{ given: null, surname_paternal: null }] },
    });
  });

  it("rejects overlong fields", () => {
    expect(toPersonCreateBody(readPersonForm(form({ given: "a".repeat(121) })))).toEqual({ ok: false, error: "tooLong" });
    expect(toPersonCreateBody(readPersonForm(form({ given: "Ana", birthDate: "1".repeat(81) })))).toEqual({
      ok: false,
      error: "tooLong",
    });
  });
});

describe("Crear espacio", () => {
  it("trims and validates the name", () => {
    expect(parseSpaceForm(form({ name: "  Familia   Prueba " }))).toEqual({ ok: true, name: "Familia Prueba" });
    expect(parseSpaceForm(form({ name: "  " }))).toEqual({ ok: false, error: "nameRequired" });
    expect(parseSpaceForm(form({ name: "x".repeat(121) }))).toEqual({ ok: false, error: "nameTooLong" });
  });
});

describe("person labels", () => {
  it("normalises GEDCOM tags and snake_case types", () => {
    expect(eventTypeKey("BIRT")).toBe("birth");
    expect(eventTypeKey("baptism")).toBe("baptism");
    expect(eventTypeKey("CHR")).toBe("baptism");
    expect(eventTypeKey("_CUSTOM")).toBe("other");
    expect(relationshipTypeKey("Parent")).toBe("parent");
    expect(relationshipTypeKey("godparent")).toBe("other");
    expect(formatName({ given: "Ana", surname_paternal: null, surname_maternal: "Ejemplo" })).toBe("Ana Ejemplo");
  });
});
