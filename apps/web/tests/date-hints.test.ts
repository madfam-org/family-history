import { createTranslator } from "next-intl";
import { describe, expect, it } from "vitest";

import en from "@messages/en.json";
import es from "@messages/es.json";
import familyEn from "@messages/family.en.json";
import familyEs from "@messages/family.es.json";

import { ApiError, codeForStatus, errorMessageKey, KNOWN_ERROR_CODES } from "@/lib/api/errors";
import { dateHint, displayDate, isDateErrorCode, normalizeDateInput } from "@/lib/dates/hints";

describe("date hints for refused free-text dates", () => {
  it("explains a bare year span as range-or-period, quoting the years", () => {
    expect(dateHint("1890-1895", "ambiguous_date")).toEqual({ key: "yearSpan", values: { from: "1890", to: "1895" } });
    expect(dateHint(" 1890 – 1895 ", "ambiguous_date").key).toBe("yearSpan");
  });

  it("asks for a four-digit year", () => {
    expect(dateHint("3/4/23", "invalid_date")).toEqual({ key: "twoDigitYear", values: { year: "23" } });
  });

  it("explains day/month/year when the month is above 12", () => {
    expect(dateHint("05/13/1923", "invalid_date")).toEqual({ key: "monthOver12", values: { day: "05", month: "13" } });
  });

  it("flags a weekday that does not match", () => {
    expect(dateHint("lunes 15 de marzo de 1923", "invalid_date").key).toBe("weekday");
  });

  it("falls back to the generic hint for each code", () => {
    expect(dateHint("por ahí del centenario", "invalid_date").key).toBe("invalid");
    expect(dateHint("3/4/1923", "ambiguous_date").key).toBe("ambiguous");
  });

  it("recognises only the two date error codes", () => {
    expect(isDateErrorCode("ambiguous_date")).toBe(true);
    expect(isDateErrorCode("invalid_date")).toBe(true);
    expect(isDateErrorCode("validation_error")).toBe(false);
  });

  it("renders every hint in both languages with the chosen values", () => {
    const tEs = createTranslator({ locale: "es", messages: familyEs, namespace: "family.dates" });
    const tEn = createTranslator({ locale: "en", messages: familyEn, namespace: "family.dates" });
    const hint = dateHint("1890-1895", "ambiguous_date");
    expect(tEs(`hints.${hint.key}`, hint.values)).toContain("entre 1890 y 1895");
    expect(tEn(`hints.${hint.key}`, hint.values)).toContain("entre 1890 y 1895");
    const two = dateHint("3/4/23", "invalid_date");
    expect(tEs(`hints.${two.key}`, two.values)).toContain("«1923»");
  });
});

describe("date display", () => {
  it("prefers the humanized date in the page language", () => {
    const event = { date_display: { es: "hacia 1890", en: "about 1890" }, date_original: "como en 1890", date_value: "ABT 1890" };
    expect(displayDate(event, "es")).toBe("hacia 1890");
    expect(displayDate(event, "en")).toBe("about 1890");
  });

  it("falls back to the text as written, then to the GEDCOM value, then to null", () => {
    expect(displayDate({ date_display: null, date_original: "hacia 1890", date_value: "ABT 1890" }, "es")).toBe("hacia 1890");
    expect(displayDate({ date_value: "ABT 1890" }, "es")).toBe("ABT 1890");
    expect(displayDate({}, "es")).toBeNull();
  });

  it("normalises spacing only", () => {
    expect(normalizeDateInput("  15  de marzo\tde 1923 ")).toBe("15 de marzo de 1923");
  });
});

describe("error code → copy", () => {
  it("has es and en copy for every known code", () => {
    for (const code of KNOWN_ERROR_CODES) {
      expect(es.errors[code], code).toBeTruthy();
      expect(en.errors[code], code).toBeTruthy();
    }
  });

  it("maps the addendum's codes to their own copy", () => {
    for (const code of ["ambiguous_date", "invalid_date", "no_relation", "relationship_exists", "download_expired"]) {
      expect(errorMessageKey(code)).toBe(code);
    }
    expect(es.errors.ambiguous_date).toMatch(/adivinar/);
    expect(es.errors.download_expired).toMatch(/venció/);
  });

  it("maps statuses and aliases for uploads and downloads", () => {
    expect(codeForStatus(410)).toBe("download_expired");
    expect(codeForStatus(413)).toBe("file_too_large");
    expect(codeForStatus(415)).toBe("unsupported_file");
    expect(errorMessageKey("payload_too_large")).toBe("file_too_large");
    expect(errorMessageKey("unsupported_media_type")).toBe("unsupported_file");
    expect(errorMessageKey("association_exists")).toBe("conflict");
    expect(errorMessageKey("association_not_found")).toBe("not_found");
    expect(new ApiError(422, "ambiguous_date", "x").code).toBe("ambiguous_date");
  });
});
