import { serializeJsonLd } from "@/lib/seo/jsonld";

/** Inline JSON-LD, rendered in the server HTML. A data block, never executed. */
export function JsonLd({ data }: { data: unknown }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: serializeJsonLd(data) }} />;
}
