import { describe, expect, it } from "vitest";

import { readPersonForm, toPersonCreateBody } from "@/lib/forms/person";
import { parseSpaceForm } from "@/lib/forms/space";
import { eventTypeKey, formatName, relationshipLabelKey } from "@/lib/people/labels";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

describe("Agregar persona", () => {
  it("maps the Mexican name model to the API body and keeps the birth date as written", () => {
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
        sex: "F",
        names: [{ given: "María Guadalupe", apellido_paterno: "Prueba", apellido_materno: "Ejemplo", nicknames: ["Lupita"] }],
      },
      birthDate: "hacia 1931",
    });
  });

  it("needs at least one name part and defaults sex to U", () => {
    const values = readPersonForm(form({ nickname: "Lupita", sex: "Z" }));
    expect(values.sex).toBe("U");
    expect(toPersonCreateBody(values)).toEqual({ ok: false, error: "nameRequired" });
    expect(toPersonCreateBody(readPersonForm(form({ maternal: "Ejemplo" })))).toEqual({
      ok: true,
      body: { sex: "U", names: [{ apellido_materno: "Ejemplo", nicknames: [] }] },
      birthDate: null,
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
    expect(formatName({ given: "Ana", apellido_paterno: null, apellido_materno: "Ejemplo" })).toBe("Ana Ejemplo");
    expect(formatName({ nombre_usado: "Chela" })).toBe("Chela");
  });

  it("reads parent-child relationships from the person's side", () => {
    const rel = { type: "parent_child", from_person_id: "parent", to_person_id: "child" };
    expect(relationshipLabelKey(rel, "child")).toBe("parentOf");
    expect(relationshipLabelKey(rel, "parent")).toBe("childOf");
    expect(relationshipLabelKey({ ...rel, type: "union" }, "parent")).toBe("union");
    expect(relationshipLabelKey({ ...rel, type: "godparent" }, "parent")).toBe("other");
  });
});
