/**
 * Loader for the counsel-reviewed privacy notice (content/aviso/<version>.<locale>.txt).
 * No legal text lives in code. A missing file reads as "not published".
 */
import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

import type { Locale } from "@/i18n/locales";

export interface AvisoBlock {
  kind: "heading" | "paragraph";
  text: string;
}

const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/;

export function isValidAvisoVersion(version: string): boolean {
  return VERSION_PATTERN.test(version) && !version.includes("..");
}

export function parseAviso(text: string): AvisoBlock[] {
  return text
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) =>
      block.startsWith("# ")
        ? { kind: "heading" as const, text: block.slice(2).trim() }
        : { kind: "paragraph" as const, text: block.replace(/\s*\n\s*/g, " ") },
    );
}

export async function loadAviso(version: string, locale: Locale): Promise<AvisoBlock[] | null> {
  if (!isValidAvisoVersion(version)) return null;
  const file = path.join(process.cwd(), "content", "aviso", `${version}.${locale}.txt`);
  try {
    const blocks = parseAviso(await readFile(file, "utf8"));
    return blocks.length > 0 ? blocks : null;
  } catch {
    return null;
  }
}
