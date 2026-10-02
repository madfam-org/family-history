import { describe, expect, it } from "vitest";

import type { NameForm } from "@/lib/api/schemas";
import {
  asId,
  associationNeedsPhrase,
  compadrazgoGroup,
  defaultSexFor,
  godparentLabelKey,
  relationshipFor,
  takesGodparents,
  takesSpouse,
} from "@/lib/forms/family";
import {
  nameFormToBody,
  nameValuesFrom,
  previewName,
  readNameValues,
  replacePrimaryName,
  splitNicknames,
  toNameFormBody,
  type NameValues,
} from "@/lib/forms/names";

const BASE: NameValues = {
  given: "Ignacio",
  paternal: "Garza",
  maternal: "Treviño",
  particlePaternal: "de la",
  particleMaternal: "",
  nombreUsado: "Nacho",
  nicknames: "",
  surnameOrder: "paterno_materno",
  sex: "M",
};

describe("Mexican name model", () => {
  it("reads and normalises the editor's fields", () => {
    const form = new FormData();
    form.set("given", "  María   Guadalupe ");
    form.set("paternal", "Castillo");
    form.set("particleMaternal", "DE LA");
    form.set("maternal", "Rosa");
    form.set("surnameOrder", "materno_paterno");
    form.set("sex", "Q");
    const values = readNameValues(form);
    expect(values.given).toBe("María Guadalupe");
    expect(values.particleMaternal).toBe("de la");
    expect(values.surnameOrder).toBe("materno_paterno");
    expect(values.sex).toBe("U");
  });

  it("builds the API name form with particles, nombre usado and apodos", () => {
    const result = toNameFormBody({ ...BASE, nicknames: "Chucho, el Güero; Chucho" });
    expect(result).toEqual({
      ok: true,
      name: {
        given: "Ignacio",
        apellido_paterno: "Garza",
        apellido_materno: "Treviño",
        particles: { paterno: "de la" },
        nombre_usado: "Nacho",
        nicknames: ["Chucho", "el Güero"],
        surname_order: "paterno_materno",
        is_primary: true,
      },
    });
  });

  it("refuses an empty name, long parts and too many apodos", () => {
    const empty = { ...BASE, given: "", paternal: "", maternal: "", nombreUsado: "" };
    expect(toNameFormBody(empty)).toEqual({ ok: false, error: "nameRequired" });
    expect(toNameFormBody({ ...BASE, given: "x".repeat(121) })).toEqual({ ok: false, error: "tooLong" });
    expect(toNameFormBody({ ...BASE, particlePaternal: "x".repeat(21) })).toEqual({ ok: false, error: "tooLong" });
    const many = Array.from({ length: 11 }, (_, index) => `apodo${index}`).join(",");
    expect(toNameFormBody({ ...BASE, nicknames: many })).toEqual({ ok: false, error: "tooManyNicknames" });
  });

  it("drops a particle whose surname is empty", () => {
    const result = toNameFormBody({ ...BASE, paternal: "", particlePaternal: "de" });
    expect(result.ok && result.name.particles).toBeFalsy();
  });

  it("splits apodos on commas and semicolons, without duplicates", () => {
    expect(splitNicknames("Lupe; Lupita, Lupe ,")).toEqual(["Lupe", "Lupita"]);
  });

  it("previews the name in the chosen surname order", () => {
    expect(previewName(BASE)).toBe("Ignacio de la Garza Treviño");
    expect(previewName({ ...BASE, surnameOrder: "materno_paterno" })).toBe("Ignacio Treviño de la Garza");
    expect(previewName({ ...BASE, surnameOrder: "single", maternal: "" })).toBe("Ignacio de la Garza");
  });

  it("replaces only the primary form and sends the others back without server fields", () => {
    const forms = [
      { id: "n1", given: "Josefa", apellido_paterno: "Luna", nicknames: [], particles: {}, extra_surnames: [], is_primary: true },
      {
        id: "n2",
        given: "Pepa",
        apellido_paterno: "Luna",
        nicknames: ["Pepita"],
        particles: { paterno: "de" },
        extra_surnames: [],
        name_type: "aka",
        surname_order: "paterno_materno",
        is_primary: false,
        position: 1,
      },
    ] as NameForm[];
    const edited = { given: "Josefa", apellido_paterno: "Luna", nicknames: [], is_primary: true };
    const bodies = replacePrimaryName(forms, edited);
    expect(bodies[0]).toBe(edited);
    expect(bodies[1]).toEqual({
      given: "Pepa",
      apellido_paterno: "Luna",
      particles: { paterno: "de" },
      nicknames: ["Pepita"],
      surname_order: "paterno_materno",
      name_type: "aka",
      is_primary: false,
    });
    expect(Object.keys(nameFormToBody(forms[1] as NameForm))).not.toContain("id");
  });

  it("prefills the editor from the primary form", () => {
    const values = nameValuesFrom(
      { given: null, nombre_de_pila: "Refugio", apellido_paterno: "Soto", nicknames: ["Cuco"], particles: {}, extra_surnames: [] } as NameForm,
      "M",
    );
    expect(values.given).toBe("Refugio");
    expect(values.nicknames).toBe("Cuco");
    expect(values.surnameOrder).toBe("paterno_materno");
  });
});

describe("relationship and godparent editors", () => {
  const qualifier = { pedigree: "adopted", status: "union_libre" } as const;

  it("creates parent_child with the parent as from_person_id", () => {
    expect(relationshipFor("mother", "ego", "rel", qualifier)).toEqual({
      type: "parent_child",
      from_person_id: "rel",
      to_person_id: "ego",
      qualifier: "adopted",
    });
    expect(relationshipFor("child", "ego", "rel", qualifier)).toEqual({
      type: "parent_child",
      from_person_id: "ego",
      to_person_id: "rel",
      qualifier: "adopted",
    });
  });

  it("creates a union with the partner status, never a marriage type", () => {
    expect(relationshipFor("partner", "ego", "rel", qualifier)).toEqual({
      type: "union",
      from_person_id: "ego",
      to_person_id: "rel",
      qualifier: "union_libre",
    });
  });

  it("gives a new father or mother a sex, and leaves the rest unknown", () => {
    expect(defaultSexFor("father")).toBe("M");
    expect(defaultSexFor("mother")).toBe("F");
    expect(defaultSexFor("child")).toBe("U");
  });

  it("offers padrinos on sacraments and XV años only", () => {
    for (const type of ["baptism", "confirmation", "first_communion", "religious_marriage", "quinceanera"]) {
      expect(takesGodparents(type), type).toBe(true);
    }
    expect(takesGodparents("civil_marriage")).toBe(false);
    expect(takesGodparents("birth")).toBe(false);
    expect(takesSpouse("religious_marriage")).toBe(true);
    expect(takesSpouse("baptism")).toBe(false);
  });

  it("labels padrino or madrina by the godparent's sex, and needs a phrase for other roles", () => {
    expect(godparentLabelKey("M")).toBe("padrino");
    expect(godparentLabelKey("F")).toBe("madrina");
    expect(godparentLabelKey("U")).toBe("padrinoNeutral");
    expect(associationNeedsPhrase("other")).toBe(true);
    expect(associationNeedsPhrase("godparent")).toBe(false);
  });

  it("groups compadrazgo relations in Spanish or English vocabulary", () => {
    expect(compadrazgoGroup("madrina")).toBe("godparents");
    expect(compadrazgoGroup("godparent")).toBe("godparents");
    expect(compadrazgoGroup("ahijada")).toBe("godchildren");
    expect(compadrazgoGroup("comadre")).toBe("compadres");
    expect(compadrazgoGroup("co_parent")).toBe("compadres");
    expect(compadrazgoGroup("testigo")).toBe("other");
  });

  it("accepts only UUID-shaped ids", () => {
    expect(asId(" 6F1C1D3E-8F0A-4B8E-9D2E-1A2B3C4D5E6F ")).toBe("6f1c1d3e-8f0a-4b8e-9d2e-1a2b3c4d5e6f");
    expect(asId("../../v1/spaces")).toBeNull();
    expect(asId(undefined)).toBeNull();
  });
});
