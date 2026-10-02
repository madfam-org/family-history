// @vitest-environment jsdom
/**
 * Client components of the wave-2 screens, rendered with Testing Library in es-MX (and en where
 * the language matters). Synthetic people from the domain lexicon.
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import en from "@messages/en.json";
import es from "@messages/es.json";
import familyEn from "@messages/family.en.json";
import familyEs from "@messages/family.es.json";

import type { PeopleSearchResult } from "@/app/actions/relatives";
import { DateField } from "@/components/family/DateField";
import { AddEventForm } from "@/components/family/EventForms";
import { ConfirmRemove } from "@/components/family/ConfirmRemove";
import { FormStatus } from "@/components/family/FormStatus";
import { PersonPicker } from "@/components/family/PersonPicker";
import { ExportFormats } from "@/components/jobs/ExportPanel";
import { ImportReport } from "@/components/jobs/ImportReport";
import { JobStatusLine } from "@/components/jobs/JobStatusLine";
import { useJob } from "@/components/jobs/useJob";
import { TreeCanvas } from "@/components/tree/TreeCanvas";
import { clientMessages } from "@/i18n/messages";
import { buildGraph } from "@/lib/tree/graph";
import { layoutAncestors } from "@/lib/tree/layout";
import type { Person } from "@/lib/api/schemas";
import type { PollResult } from "@/lib/jobs/polling";

const SPACE = "6f1c1d3e-8f0a-4b8e-9d2e-1a2b3c4d5e6f";
const JESUS = "1b9c6d3f-8e52-4b9f-8b1c-1d2e3f4a5b6c";

function wrap(children: ReactNode, locale: "es" | "en" = "es") {
  const messages = locale === "es" ? { ...es, ...familyEs } : { ...en, ...familyEn };
  return (
    <NextIntlClientProvider locale={locale} messages={clientMessages(messages)} timeZone="America/Mexico_City">
      {children}
    </NextIntlClientProvider>
  );
}

beforeAll(() => {
  // jsdom has no ResizeObserver; the tree only needs it to learn its size.
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

afterEach(() => cleanup());

describe("DateField", () => {
  it("always lists examples and explains a refused date in Spanish", () => {
    render(wrap(<DateField name="date" label="Fecha" defaultValue="1890-1895" hint={{ key: "yearSpan", values: { from: "1890", to: "1895" } }} />));
    const input = screen.getByLabelText("Fecha");
    expect(input).toHaveProperty("value", "1890-1895");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("entre 1890 y 1895");
    expect(input.getAttribute("aria-describedby")).toContain(alert.id);
    expect(screen.getByText("hacia 1890")).toBeTruthy();
  });

  it("has no alert when there is nothing to explain", () => {
    render(wrap(<DateField name="date" label="Fecha" defaultValue="" />));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("PersonPicker", () => {
  it("searches after two letters, lists results as radios and posts the choice", async () => {
    const search = vi.fn(
      async (): Promise<PeopleSearchResult> => ({
        ok: true,
        items: [
          {
            id: JESUS,
            display_name: "Jesús Ortega Vega",
            sex: "M",
            living_status: "deceased",
            birth: { date_value: "1921", date_display: { es: "1921", en: "1921" }, place: null },
          },
        ],
      }),
    );
    const { container } = render(wrap(<PersonPicker spaceId={SPACE} name="relativeId" search={search} />));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "C" } });
    expect(search).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Chucho" } });
    const option = await screen.findByRole("radio", { name: /Jesús Ortega Vega/ });
    expect(search).toHaveBeenCalledWith(SPACE, "Chucho");
    expect(screen.getByText("1 resultado")).toBeTruthy();
    fireEvent.click(option);
    expect(screen.getByRole("status").textContent).toContain("Elegiste a Jesús Ortega Vega");
    expect(container.querySelector<HTMLInputElement>('input[name="relativeId"]')?.value).toBe(JESUS);
  });

  it("shows search failures with the mapped copy", async () => {
    const search = vi.fn(async (): Promise<PeopleSearchResult> => ({ ok: false, code: "rate_limited" }));
    render(wrap(<PersonPicker spaceId={SPACE} name="relativeId" search={search} />));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Petra" } });
    await waitFor(() => expect(screen.getByText(/La búsqueda falló: Demasiadas solicitudes/)).toBeTruthy());
  });
});

describe("ConfirmRemove", () => {
  it("asks before removing and gives focus back on cancel", async () => {
    const action = vi.fn(async () => ({ status: "saved" as const, count: 1 }));
    render(
      wrap(
        <ConfirmRemove
          action={action}
          field="relationshipId"
          id="r-1"
          label="Quitar la relación con Petra Ramírez Luna"
          question="¿Quitar la relación con Petra Ramírez Luna?"
          done="Relación quitada."
        />,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Quitar la relación con Petra Ramírez Luna" }));
    const question = screen.getByText("¿Quitar la relación con Petra Ramírez Luna?");
    await waitFor(() => expect(document.activeElement).toBe(question));
    expect(screen.getByRole("button", { name: "Sí, quitar" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Quitar la relación con Petra Ramírez Luna" })),
    );
    expect(action).not.toHaveBeenCalled();
  });
});

describe("FormStatus", () => {
  it("shows failures with Spanish copy, never the API's message", () => {
    render(wrap(<FormStatus state={{ status: "failed", code: "relationship_exists", values: {} }} saved="Listo" />));
    expect(screen.getByRole("alert").textContent).toBe("Esa relación ya está registrada.");
  });

  it("leaves a refused date to the date field", () => {
    render(
      wrap(
        <FormStatus
          state={{ status: "failed", code: "ambiguous_date", values: {}, dateHint: { key: "ambiguous", values: {} } }}
          saved="Listo"
        />,
      ),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("AddEventForm", () => {
  it("offers every editable event type and asks for the spouse only on marriages", () => {
    render(wrap(<AddEventForm personId="p" spaceId={SPACE} partners={[{ id: JESUS, name: "Jesús Ortega Vega" }]} />));
    const type = screen.getByLabelText("Tipo de evento");
    expect(within(type).getByRole("option", { name: "XV años" })).toBeTruthy();
    expect(screen.queryByLabelText("Con quién")).toBeNull();
    fireEvent.change(type, { target: { value: "religious_marriage" } });
    expect(screen.getByLabelText("Con quién")).toBeTruthy();
  });
});

describe("jobs", () => {
  it("shows the import report in Spanish", () => {
    render(
      wrap(
        <ImportReport
          report={{
            source_product: "Programa de ejemplo",
            source_version: "5.5.1",
            record_counts: { INDI: 3, FAM: 1, _LOC: 2 },
            diagnostics: [
              { severity: "warning", code: "dual_year", message: "Converted", line: 12 },
              { severity: "error", code: "bad_pointer", line: 30 },
            ],
            extension_tags: { _MILT: 1 },
          }}
        />,
      ),
    );
    expect(screen.getByText("Personas")).toBeTruthy();
    expect(screen.getByText("Familias")).toBeTruthy();
    expect(screen.getByText("Otros registros (_LOC)")).toBeTruthy();
    expect(screen.getByText("2 avisos")).toBeTruthy();
    expect(screen.getByText("Error (1)")).toBeTruthy();
    expect(screen.getByText("_MILT")).toBeTruthy();
    expect(screen.getByText(/Origen: Programa de ejemplo/)).toBeTruthy();
  });

  it("explains known diagnostic codes in Spanish and labels a native file's sections", () => {
    render(
      wrap(
        <ImportReport
          report={{
            source_version: null,
            source_product: null,
            record_counts: { people: 2, unions: 1 },
            created_records: { people: 2, parent_child: 1 },
            diagnostics: [
              { severity: "warning", code: "date_kept_as_text", message: "Kept as text", line: null },
              { severity: "info", code: "brand-new-code", message: "Something new", line: 4 },
            ],
            extension_tags: {},
          }}
        />,
      ),
    );
    expect(screen.getAllByText("Personas")).toHaveLength(2);
    expect(screen.getByText("Vínculos de madre o padre con hijos")).toBeTruthy();
    expect(screen.getByText(/se guardó tal como venía escrita/)).toBeTruthy();
    expect(screen.getByText("brand-new-code")).toBeTruthy();
    expect(screen.getByText(/Detalle técnico \(en inglés\): Something new/)).toBeTruthy();
  });

  it("says when a finished import sent no report", () => {
    render(wrap(<ImportReport report={null} />));
    expect(screen.getByText(/no envió el detalle/)).toBeTruthy();
  });

  it("maps a failed job's error code to copy", () => {
    render(
      wrap(
        <JobStatusLine
          view={{
            job: { id: "j", kind: "gedcom_import", status: "failed", error_code: "gedcom_invalid", created_at: "2026-10-01T12:00:00Z" },
            error: null,
            stopped: false,
          }}
        />,
      ),
    );
    expect(screen.getByRole("status").textContent).toContain("No se pudo completar");
    expect(screen.getByRole("alert").textContent).toContain("No pudimos leer ese archivo como GEDCOM");
  });

  it("offers the four export formats, explained in plain language", () => {
    render(wrap(<ExportFormats locale="es" spaceId={SPACE} />));
    for (const name of ["GEDZIP (GEDCOM 7 con fotos)", "GEDCOM 7", "GEDCOM 5.5.1", "Copia completa (JSON)"]) {
      expect(screen.getByRole("heading", { name })).toBeTruthy();
    }
    expect(screen.getAllByRole("button", { name: /Preparar descarga/ })).toHaveLength(4);
  });
});

describe("useJob", () => {
  function Probe({ poll }: { poll: (id: string) => Promise<PollResult> }) {
    const view = useJob("job-1", poll);
    return wrap(<JobStatusLine view={view} />);
  }
  const job = (status: "queued" | "succeeded") => ({
    ok: true as const,
    job: { id: "job-1", kind: "export", status, created_at: "2026-10-01T12:00:00Z" },
  });

  it("polls until the job finishes, then stops", async () => {
    const poll = vi.fn<(id: string) => Promise<PollResult>>().mockResolvedValueOnce(job("queued")).mockResolvedValue(job("succeeded"));
    render(<Probe poll={poll} />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("En espera"));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Listo"), { timeout: 3000 });
    const calls = poll.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(poll.mock.calls.length).toBe(calls);
  });

  it("keeps polling while the page is hidden", async () => {
    const hidden = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    const poll = vi.fn<(id: string) => Promise<PollResult>>().mockResolvedValue(job("queued"));
    render(<Probe poll={poll} />);
    await waitFor(() => expect(poll).toHaveBeenCalledTimes(1));
    hidden.mockRestore();
  });

  it("stops on a final error and shows it", async () => {
    const poll = vi.fn(async (): Promise<PollResult> => ({ ok: false, code: "not_found", retry: false }));
    render(<Probe poll={poll} />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("No encontramos lo que buscas."));
  });
});

describe("TreeCanvas", () => {
  const people = (["ego", "dad", "mom"] as const).map((id) => ({
    id,
    display_name: { ego: "Regina Castillo Ramírez", dad: "Ignacio Castillo Soto", mom: "Leticia Ramírez Luna" }[id],
    sex: id === "dad" ? "M" : "F",
    living_status: "deceased",
    visibility: "space",
    birth: null,
    death: null,
    names: [],
    events: [],
    citations: [],
    relationships:
      id === "ego"
        ? [
            { id: "r1", type: "parent_child", from_person_id: "dad", to_person_id: "ego", qualifier: "birth" },
            { id: "r2", type: "parent_child", from_person_id: "mom", to_person_id: "ego", qualifier: "adopted" },
          ]
        : [],
  })) as unknown as Person[];
  const graph = buildGraph(people, "es");
  const layout = layoutAncestors(graph, "ego", 4);

  it("draws every person as a link card and zooms with the buttons", async () => {
    const { container } = render(
      wrap(
        <TreeCanvas
          layout={layout}
          people={Object.fromEntries(graph.people)}
          href={{ prefix: "/es/personas/", suffix: "/arbol" }}
          label="Árbol de Regina Castillo Ramírez"
        />,
      ),
    );
    const group = screen.getByRole("group", { name: "Árbol de Regina Castillo Ramírez" });
    expect(group.getAttribute("tabindex")).toBe("0");
    const card = screen.getByRole("link", { name: "Ver el árbol de Ignacio Castillo Soto" });
    expect(card.getAttribute("href")).toBe("/es/personas/dad/arbol");
    expect(container.querySelectorAll("path[stroke-dasharray]")).toHaveLength(1);
    const svg = container.querySelector("svg.size-full");
    const before = svg?.getAttribute("viewBox");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /Acercar/ })));
    expect(svg?.getAttribute("viewBox")).not.toBe(before);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("moves with the arrow keys", async () => {
    const { container } = render(
      wrap(
        <TreeCanvas
          layout={layout}
          people={Object.fromEntries(graph.people)}
          href={{ prefix: "/en/personas/", suffix: "/arbol" }}
          label="Tree"
        />,
        "en",
      ),
    );
    const svg = container.querySelector("svg.size-full");
    const before = svg?.getAttribute("viewBox");
    await act(async () => fireEvent.keyDown(screen.getByRole("group", { name: "Tree" }), { key: "ArrowRight" }));
    expect(svg?.getAttribute("viewBox")).not.toBe(before);
    expect(screen.getByRole("button", { name: /Zoom in/ })).toBeTruthy();
  });
});
