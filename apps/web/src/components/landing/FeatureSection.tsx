export interface Feature {
  key: string;
  title: string;
  body: string;
}

export function FeatureSection({
  id,
  title,
  lead,
  features,
  tone = "plain",
  highlightKey,
}: {
  id: string;
  title: string;
  lead: string;
  features: readonly Feature[];
  tone?: "plain" | "amate";
  /** A feature that gets the seasonal cempasúchil fill (decorative bar, never text). */
  highlightKey?: string;
}) {
  const wrapper = tone === "amate" ? "bg-amate text-bark" : "";
  const card = tone === "amate" ? "rounded-xl bg-bg/60 p-5 text-fg" : "fh-card";
  return (
    <section id={id} aria-labelledby={`${id}-titulo`} className={wrapper}>
      <div className="fh-container py-12">
        <h2 id={`${id}-titulo`} className={`text-3xl font-bold ${tone === "amate" ? "text-bark" : ""}`}>
          {title}
        </h2>
        <p className={`mt-2 max-w-2xl ${tone === "amate" ? "text-bark" : "text-muted"}`}>{lead}</p>
        <ul className="mt-8 grid gap-4 sm:grid-cols-2">
          {features.map((feature) => (
            <li key={feature.key} className={card}>
              {feature.key === highlightKey ? (
                <span aria-hidden="true" className="mb-3 block h-1.5 w-12 rounded-full bg-cempasuchil" />
              ) : null}
              <h3 className="text-xl font-bold">{feature.title}</h3>
              <p className="mt-2">{feature.body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
