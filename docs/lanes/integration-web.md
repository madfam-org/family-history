# Lane notes: integration, web (wave 2)

> Last Updated: 2026-10-01

Lane INT-WEB built the web side of the wave-2 contract addendum: free-text dates, the Mexican
name model, relationship and godparent editors, compadrazgo, the family tree, the kinship
lookup, GEDCOM import and the «Llévate todo» export. It follows the patterns in
[web.md](./web.md): brand from `brand.ts`, host routing, the zod API client and es/en message
parity.

**Branch history.** The branch started stacked on PR #4 (`feat/web-landing-and-app-shell`) at
`c8f8a24`, #4's head after the coordinator's `update-branch`. The original #4 head was
`000b37c`. #4 squash-merged into `main` on 2026-10-01, and this branch was rebased with
`git rebase --onto origin/main c8f8a24`, so it carries only this lane's commits.

## Screens (es-MX first, en second)

| Path (app host) | What it does |
|---|---|
| `/es/personas/<id>` | Privacy badge «Persona viva — solo la ve tu familia» when the person is private, and a «Dato sensible · religión» marker on sensitive events. Events show `date_display`; sacramental events list padrinos and madrinas, with add and remove. Relatives are listed by name, with pedigree or partner status, and each can be removed after a confirmation step. Also: «Agregar familiar», the compadrazgo panel, and links to edit, the tree and the kinship lookup |
| `/es/personas/<id>/editar` | Name editor: nombre(s), apellido paterno and materno with particles («de la»), nombre usado, apodos and surname order, with a live preview. Events: «Corregir fecha» per event and «Agregar evento», which takes a free-text date and, for marriages, the spouse. Refused dates show a hint chosen for the text that was typed |
| `/es/personas/<id>/arbol` | The tree: ancestors (pedigree), or descendants with `?vista=descendientes`. Pan, pinch, wheel, buttons and the keyboard; a legend of line styles; the same tree as a nested list |
| `/es/familias/<id>/parentesco` | «¿Cómo estamos emparentados?»: pick two people (`?de=&a=`, ids only) and read `label_es`, for example «Porfirio Castillo Méndez es bisabuelo de Romina Torres Castillo». A «Verlo al revés» link swaps the two |
| `/es/familias/<id>/importar` | Stewards and editors only. Upload a `.ged`, a `.gdz` or a native `.json` (a «Llévate todo» copy) up to 25 MiB (checked before upload), follow the job, then read the report in Spanish: what was added, what the file held, every warning by severity and line (common codes explained in Spanish, the English message kept under «Detalle técnico»), and other programs' extension tags (the platform's own `_FH_` tags are not listed). A failed job shows its `error_code` copy, for example `gedcom_invalid` |
| `/es/familias/<id>/exportar` | «Llévate todo»: the four formats in plain Spanish, «Gratis para todas las familias, siempre. No depende de ningún plan.», job polling, the download, and the 24-hour expiry. Nothing on the page checks a plan or a role |
| `/es/familias/<id>` | The «Próximamente» tree placeholder is replaced by the space's tools: kinship, import (stewards and editors) and export. The people list shows `date_display` and «Privada» |

Adding a person now sends the birth date as `date_original`. When the API refuses it, the editor
opens with `?fecha=ambiguous_date|invalid_date` and a hint. Only the error kind goes into the URL,
never the text.

### Route handlers (app host only)

The browser cannot reach the API directly, because the API client is server-side
(`FH_API_INTERNAL_URL`). So the app gained three route handlers under `/api/app/`. Host routing
passes them on the app host and returns 404 on the landing host. The proxy runs the same
session rotation for them as for pages.

| Route | Does |
|---|---|
| `POST /api/app/spaces/<id>/imports` | Checks the request is same-origin and multipart. It returns 413 when the declared length passes 25 MiB plus 64 KiB of envelope, and a byte counter enforces the same limit while streaming. The body streams to the API and is never buffered whole |
| `GET /api/app/jobs/<id>` | The job, for polling, sent `no-store` |
| `GET /api/app/jobs/<id>/download?volver=<app path>` | Streams the file. Only `content-type`, `content-length` and `content-disposition` pass through. On any error it answers 303 back to `volver` (checked with `safeReturnTo`) with `?error=<code>`, so a 410 reads as «Este enlace ya venció» |

`next.config.ts` sets `experimental.proxyClientMaxBodySize: "26mb"`. The proxy buffers request
bodies up to this size; the default is 10 MB, and a larger upload would be cut short.

Server actions stay at the 64 KB limit. Uploads never go through a server action.

### Job polling

Polling starts at 1 s and backs off ×1.5 to a 10 s ceiling. While the page is hidden it keeps
polling at the ceiling rather than pausing. The preview browser reports `hidden` for a pane that is
not on screen, and so do some in-app browsers; a pause there left the page stuck on «Revisando
el avance…».

Failures that will not fix themselves stop polling and show the error: `unauthorized`,
`forbidden`, `not_found` and `early_access_required`. Every other failure is shown while polling
keeps retrying.

## Tree: why hand-written SVG

These candidates were checked from the npm tarballs of the exact versions on 2026-10-01:

| | family-chart 0.9.0 | Topola 3.10.4 | Hand-written SVG (chosen) |
|---|---|---|---|
| Licence | `LICENSE.txt` MIT, but `package.json` says ISC (they disagree) | `LICENSE` Apache-2.0 | AGPL-3.0, this repo |
| Dependencies | all of `d3` ^7.9 | six d3 modules, `parse-gedcom`, `array-flat-polyfill` | none |
| Size | 106 KB minified, plus d3 | 222 KB unpacked, plus its dependencies | two pure modules and one component |
| React 19 | no React integration; imperative DOM | no React integration; imperative d3 | React-rendered |
| Strict CSP | builds cards with `innerHTML` that holds `style="…"` attributes, which our nonce CSP (`style-src` without `'unsafe-inline'`) blocks | d3 sets inline styles imperatively | no `style` attributes; classes in `globals.css`. A test asserts no `[style]` |
| Our model | — | GEDCOM FAM-shaped couples | pedigree line styles, several partners, repeated people as stubs, and a list outline from the same walk |

Both libraries would have been client-only islands driving the DOM outside React, and
family-chart would have needed a CSP exception. The custom layout:
- `lib/tree/graph.ts` builds the graph;
- `lib/tree/layout.ts` does a tidy-tree walk that returns grid positions plus the accessible
  outline;
- `lib/tree/geometry.ts` holds the paths and the camera maths.

All three are pure and tested. `TreeCanvas` is a client component, but it reads no browser API
during render, so it server-renders safely and hydrates for the gestures.

Line styles show the pedigree, so colour is never the only cue: solid for birth, dashed for
adoption, dotted for foster, dash-dot for step. A couple's union is an accent line, dashed when
separated or divorced. Partner cards have a dashed border.

**Data.** There is no graph endpoint, so the page walks `GET /v1/people/{id}`:
- 4 generations up, or 3 down;
- at most 80 people, 6 at a time;
- the cap and any relative that failed to load are shown, not hidden.

## Dependencies added

All are dev-only and pinned exactly. No runtime dependency was added.

| Package | Version | Licence | Why |
|---|---|---|---|
| `@testing-library/react` | 16.3.3 | MIT | Component tests (React 19 peer range) |
| `@testing-library/dom` | 10.4.2 | MIT | Peer of the above |
| `jsdom` | 27.4.0 | MIT | DOM for component tests. Version 27 supports Node 20.19 and 22.12+; jsdom 30 needs Node 22.22+ |

`pnpm audit --audit-level critical`: no known vulnerabilities.

## Tests and gates

`pnpm --filter @family-history/web run lint|typecheck|test|build` all pass. There are 235 Vitest
tests in 20 files (plus one that runs only once `packages/contracts/openapi.json` holds the #17
contract); wave 1 had 107 in 13. New files:
- `openapi-conformance.test.ts`: conformance with #17's OpenAPI contract (below);
- `addendum-schemas.test.ts`: the addendum's response shapes through zod, and the endpoints that
  send its requests;
- `date-hints.test.ts`: hint selection and rendering in both languages, date display, and error
  code → copy for every known code;
- `tree-layout.test.ts`: graph, ancestors, descendants, several partners, adoption, foster and
  step, pedigree collapse, depth limits and geometry;
- `family-forms.test.ts`: the name model and the relationship and godparent rules;
- `jobs.test.ts`: polling, file checks, and the upload, status and download handlers;
- `components.test.tsx` (jsdom): DateField, PersonPicker, ConfirmRemove, FormStatus,
  AddEventForm, ImportReport, JobStatusLine, useJob, ExportFormats and TreeCanvas.

Message parity covers `family.<locale>.json`, which `src/i18n/messages.ts` merges with
`<locale>.json`. Client components get only the `family` and `errors` namespaces, through a
`NextIntlClientProvider` in the workspace layout. The largest new source file is
`src/lib/api/schemas.ts` at under 300 lines.

### Conformance with the API's contract

`tests/fixtures/openapi-v1-web.json` vendors the component schemas the web touches from #17's
`packages/contracts/openapi.json` (`d1dd43b`): the 13 responses it parses, the 7 request bodies
it sends, and their dependencies (51 schemas). `tests/support/openapi.ts` generates payloads from
them and validates bodies against them. The test:
- feeds every response component to the matching zod schema three ways: every field filled,
  required fields only with nulls, and one variant per enum value;
- checks that the web's enums (living status, sex, role, visibility, job status, export
  formats, association roles, editable event types) match the API's;
- validates every request body the web builds (person create and patch, event create and
  patch, relationships for each relative kind, associations, exports) against the API's input
  schemas, which reject unknown fields;
- compares the vendored copy with `packages/contracts/openapi.json` once that file holds the
  #17 contract (it holds `KinshipOut`), so drift fails CI after #17 merges.

A deliberate break (dropping `presumed_deceased`, narrowing an association's `sex`) makes four
of these tests fail, so they bite.

### Checked against the real API

#17's API (`d1dd43b`, from the INT-API clone's own virtualenv) ran locally with:
- `FH_ENV=local`, `FH_AUTH_DISABLED=true` (its synthetic principal);
- a throwaway Homebrew PostgreSQL 14 cluster, with the app role `NOSUPERUSER NOBYPASSRLS` owning
  the database and `pg_trgm` installed;
- migrations at head, plus `python -m family_history.worker`.

The web's production build ran against it with a locally minted session. All data was synthetic:
the repo's `api/tests/fixtures/gedcom/familia-sintetica-7.ged`.

1. **Import through the web.** `POST /api/app/spaces/<id>/imports` returned `202`, and
   `GET /api/app/jobs/<id>` reached `succeeded`. The report was in the final shape: `record_counts`
   by tag, `created_records` by row, 3 diagnostics and the extension tags. The import page
   rendered it in Spanish.
2. **Every page parses real responses.** On the space page, and on each of the 4 imported people's
   page, editor, and both tree views, nothing showed an alert and every `<h1>` showed the formal
   `display_name`.
   - The padrino on Silverio's baptism showed from `Event.associations` (`display_name`, `sex: U`),
     with no extra fetch.
   - Kinship read «Tomasa Moreno Reyes es madre de Consuelo Cortés Moreno», and `404 no_relation`
     showed the notice.
3. **Export through the web.** «Preparar descarga» for the JSON copy (the server action) moved to
   `?trabajo=`, polled to «Listo», and showed the expiry. The download through
   `/api/app/jobs/<id>/download` came back `application/json` with
   `filename="family-history-2026-10-01.json"`.
4. **Re-import.** The downloaded `.json` was uploaded into a second space through the same route
   handler. It succeeded with the same counts (4 people, 10 events, 5 places, 1 union,
   2 parent–child links and so on) and no diagnostics. Exporting the second space gave a file
   **byte-identical** to the first export.
5. **Filenames.** The GEDCOM 7, GEDZIP and 5.5.1 exports downloaded as `….ged`, `….gdz` and
   `…-gedcom551.ged`.
6. **Failures.** A text file named `.ged` failed the job with `gedcom_invalid`, and the import page
   showed «No pudimos leer ese archivo como GEDCOM…». A `.txt` upload came back as
   `415 unsupported_file` through the handler.

No console errors. The server, the worker, Postgres and the browser tab were stopped afterwards.

**Not checked:**
- a real Janua token; the API ran with its synthetic principal;
- `docker build`, which CI's image job covers.

## Alignment with the final contract (INT-API #17)

The mismatches raised during the lane were all settled by #17, and the web now follows its final
contract:

| Topic | Final contract | Web |
|---|---|---|
| Kinship | `{kinship: {kind, up, down, half, adoptive, partner_status, via}, label_es, label_en}`; `404 person_not_found`, `404 no_relation` | Strict object schema. `no_relation` → «No encontramos un parentesco…»; `person_not_found` → «No encontramos a una de las dos personas…» |
| Associations | `Event.associations[]` = `{id, person_id, display_name, sex, role, phrase}` | Padrino, madrina or neutral from `sex`, or the recorded phrase; the per-godparent fetch is gone |
| `display_name` | FORMAL: nombre de pila and surnames | Headings and pickers use it; the person page shows «Nombre que usaba: …» and «Apodos: …» under the heading |
| Import report | Exactly `ImportReport` | Labels both tag counts and row counts (`people`, `unions`, `parent_child`…). Spanish copy for the 13 importer codes and 22 common engine codes; the code and the English message are always shown |
| Imports | `.ged`, `.gdz`, native `.json`, 25 MiB | Picker, client check and copy accept `.json`; the route handler leaves type checks to the API (`415 unsupported_file`) |
| Errors | `413 file_too_large`, `415 unsupported_file`, `410 download_expired`, plus `empty_file`, `job_not_ready`, `association_is_principal`, `no_download`, `invalid_cursor` | Own copy for the first set and `empty_file`, `job_not_ready`, `association_is_principal`; aliases for the rest |
| Job `error_code` | `gedcom_invalid`, `native_export_invalid`, `insufficient_role`, `not_a_member`, `invalid_format`, `worker_timeout`, `internal_error` | Own es/en copy for `gedcom_invalid`, `native_export_invalid` and `worker_timeout`; the others map to forbidden, validation or server copy |
| Downloads | `Content-Disposition` with `.ged`, `.gdz`, `-gedcom551.ged`, `.json` | Passed through unchanged |
| Citing an event | Assertion `{subject_type: "event", field: "occurred", value: true, citation_ids}` | Noted only; no citation UI in this lane |

**Still open (later waves):** `GET /v1/people/{id}/tree?up=&down=`. The tree still walks one person
at a time, capped at 80. The rest of the diagnostic codes have English messages only.

## Requests for other owners

- **`docs/ARCHITECTURE.md`** (coordinator). Add the addendum endpoints to the v1 table. Under
  Hosts, note that `/api/app/*` is the web's own route-handler prefix, app host only. Note that
  the web sets `proxyClientMaxBodySize` to 26 MB for imports.
- **`docs/HONEST_STATUS.md`.**
  - The tree view, the editors, the kinship lookup, import and export now exist in the web, and
    are not deployed.
  - Import → export → re-import was checked locally against #17's API, not in any deployed
    environment.
  - Editing places and visibility is not built.
- **The `README` and llms files** should describe import and export only once #14 and #17 are
  both merged and deployed.

## Known limits

- Events take no place yet: the API needs a `place_id`, and there is no place picker.
- `is_private` and `visibility` are displayed but not editable here.
- The spouse on a marriage event comes only from already-recorded partners.
- The person picker uses a server action, so searches are POSTs and Next runs them one after
  another; it is debounced by 300 ms.
