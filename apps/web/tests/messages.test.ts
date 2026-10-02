import { describe, expect, it } from "vitest";

import en from "@messages/en.json";
import es from "@messages/es.json";

import { brand } from "@/lib/brand";

type Tree = { [key: string]: string | Tree };

function leaves(tree: Tree, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out.set(path, value);
    else for (const [nested, text] of leaves(value, path)) out.set(nested, text);
  }
  return out;
}

const esLeaves = leaves(es as Tree);
const enLeaves = leaves(en as Tree);

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{(\w+)[,}]|<(\w+)>/g)].map((match) => match[1] ?? match[2] ?? "").sort();
}

describe("message files", () => {
  it("have the same keys in es and en", () => {
    expect([...enLeaves.keys()].sort()).toEqual([...esLeaves.keys()].sort());
  });

  it("have no empty strings", () => {
    for (const [key, value] of [...esLeaves, ...enLeaves]) expect(value.trim(), key).not.toBe("");
  });

  it("use the same placeholders and tags in both languages", () => {
    for (const [key, value] of esLeaves) expect(placeholders(enLeaves.get(key) ?? ""), key).toEqual(placeholders(value));
  });

  it("never hard-code the brand name (it comes from lib/brand.ts)", () => {
    const names = [...Object.values(brand.displayName)];
    for (const [key, value] of [...esLeaves, ...enLeaves]) {
      for (const name of names) expect(value.includes(name), `${key} contains "${name}"`).toBe(false);
    }
  });

  it("mention no price (MADFAM rulings R9/R28)", () => {
    for (const [key, value] of [...esLeaves, ...enLeaves]) {
      expect(value, key).not.toMatch(/\$\s?\d|\bMXN\b|\bUSD\b|precio|price|\/mes|per month|gratis por|free trial/i);
    }
  });
});
