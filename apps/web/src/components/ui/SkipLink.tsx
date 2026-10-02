export function SkipLink({ label }: { label: string }) {
  return (
    <a
      href="#contenido"
      className="sr-only rounded-md bg-accent px-4 py-2 font-semibold text-on-accent focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50"
    >
      {label}
    </a>
  );
}
