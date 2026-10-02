import type { FaqItem } from "@/lib/landing/faq";

/** The visible FAQ. Pure (props in, markup out) so its parity with the JSON-LD is testable. */
export function FaqSection({ title, items }: { title: string; items: readonly FaqItem[] }) {
  return (
    <section id="preguntas" aria-labelledby="preguntas-titulo" className="fh-container py-12">
      <h2 id="preguntas-titulo" className="text-3xl font-bold">
        {title}
      </h2>
      <dl className="mt-6 divide-y divide-line">
        {items.map((item) => (
          <div key={item.key} className="py-5" data-faq-item={item.key}>
            <dt className="text-lg font-semibold" data-faq-question>
              {item.question}
            </dt>
            <dd className="mt-2 text-muted" data-faq-answer>
              {item.answer}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
