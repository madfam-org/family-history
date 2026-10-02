/** Site-level /llms.txt: plain product facts, consistent with docs/HONEST_STATUS.md. */
import { brand, brandName, brandTagline } from "@/lib/brand";

export function buildLlmsTxt(landingOrigin: string): string {
  return [
    `# ${brandName("en")} (${brandName("es")})`,
    "",
    `> ${brandTagline("en")} / ${brandTagline("es")}`,
    "",
    "An open-source (AGPL-3.0-only), Spanish-first family-history platform for Mexican and binational families.",
    "Families build their tree from evidence (civil records, parish books, oral interviews) and keep stories, photos and voice interviews in the same place.",
    "",
    "## Status",
    "",
    "- Invitation-only early access. Not open to the public. No pricing is published.",
    "- In development: the tree view, stories, voice interviews, media and exports. Do not describe them as available.",
    "",
    "## Commitments",
    "",
    "- Living people are private by default: anyone not proven dead and born within the last 110 years, or with no known birth date, is visible only inside their family space.",
    "- No DNA or genetic data, no CURP collection, no data sale, no training of models on family content.",
    "- Full export (GEDCOM 7 GEDZIP, GEDCOM 5.5.1, native JSON) is free for every family.",
    "- Spanish (es-MX) first, English second.",
    "",
    "## Links",
    "",
    `- [Landing (Spanish)](${landingOrigin}/es)`,
    `- [Landing (English)](${landingOrigin}/en)`,
    `- [Source code](${brand.sourceCodeUrl})`,
    `- [${brand.organization.legalName}](${brand.organization.url}), Cuernavaca, Morelos, Mexico`,
    "",
  ].join("\n");
}
