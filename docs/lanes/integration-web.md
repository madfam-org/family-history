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
| `/es/familias/<id>/importar` | Stewards and editors only. Upload a `.ged` or `.gdz` up to 25 MiB (checked before upload), follow the job, then read the report in Spanish: what was added, what the file held, every warning by severity and line, and other programs' extension tags |
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

`pnpm --filter @family-history/web run lint|typecheck|test|build` all pass. There are 211 Vitest
tests in 19 files; wave 1 had 107 in 13. New files:
- `addendum-schemas.test.ts`: every addendum response shape through zod, and the endpoints that
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
`src/lib/api/schemas.ts` at 261 lines.

**Checked by hand.** The production build ran against a synthetic mock API (scratchpad only, not
committed) with a locally minted session, at 360 px. Checked:
- the person page;
- the tree, both views;
- the editor's `1890-1895` → «entre 1890 y 1895 … de 1890 a 1895» hint;
- the padrino search, where «Chucho» finds Jesús;
- the kinship answer;
- export: polling, download, and the 303 back on failure;
- import: upload through the proxy, polling and the report;
- `en` pages, and `/api/app/*` returning 404 on the landing host.

No console errors and no CSP violations.

**Not checked.** Any of this against the real API: the jobs endpoints are not in INT-API's branch
yet (see below). `docker build` was not run locally either.

## Contract mismatches for the coordinator (INT-WEB ↔ INT-API)

Compared against `feat/api-integration-domain-gedcom` (PR #17) at `c6c2640`.

1. **Kinship `kinship` field shape.** The addendum lists `{kinship, label_es, label_en}`. INT-API
   returns `kinship` as an object (`KinshipStructure`: kind, up, down, half, adoptive,
   partner_status, via). The web accepts either the object or a string, and shows only the
   labels.
   - Request: record the object shape in the addendum.
2. **The full `Person` has no `birth` or `death` brief.** The wave-1 web schema extended
   `PersonSummary`, so it required both; every person page would have failed with
   `invalid_response` against the real API. Fixed on the web side, which now reads vital dates
   from `events`.
   - No API change is needed. Optionally, add the briefs to `Person` for symmetry.
3. **Where associations come back.** The addendum defines POST and DELETE only. INT-API returns
   them on `Event.associations` as `{id, person_id, role, phrase}`, and the web relies on that to
   list and remove padrinos.
   - Request: add it to the addendum.
   - There is no `display_name` or `sex`, so the web fetches each godparent separately to say
     padrino or madrina.
   - Request: add `display_name` and `sex` to `EventAssociation`.
4. **The job `report` shape is open.** The web reads the GEDCOM engine's `ImportReport`:
   `source_version`, `source_product`, `record_counts`, `created_records`,
   `diagnostics[{severity, code, message, line}]` and `extension_tags`. It also tolerates
   `counts`, `warnings` and `extensions`.
   - Request: fix the report shape in the addendum.
   - Diagnostic `message` is English. The web shows the code and line, and the message only under
     «Detalle técnico (en inglés)».
   - Request: a stable catalogue of diagnostic codes, so they can be translated.
5. **Job endpoints are not on INT-API's branch yet.** The `JobKind`, `JobStatus` and
   `ExportFormat` enums exist, but there are no routers for `/imports`, `/exports` or `/jobs` at
   `c6c2640`. The web is built to the addendum and has only run against the mock.
   - `kind` will be `gedcom_import` or `export`; the web does not depend on it.
6. **Upload error codes are not named.** The web maps HTTP 413 to `file_too_large`, 415 to
   `unsupported_file` and 410 to `download_expired`. It also accepts the aliases
   `payload_too_large`, `unsupported_media_type`, `unsupported_format`, `gone`, `job_expired` and
   `export_expired`.
   - Request: name the codes for over 25 MiB, a wrong extension, a malformed GEDCOM (a job
     `error_code`), and an expired download.
7. **Other new codes.**
   - `unknown_event` (422 from associations) maps to «No encontramos lo que buscas».
   - `association_exists` maps to the conflict copy, through the `_exists` suffix rule.
   - `association_not_found` and `job_not_found` map to not found.
   - `relationship_exists` has its own copy.
8. **`date_original` length.** INT-API accepts up to 200 characters; the web caps it at 80, the
   wave-1 limit. Both are fine. Tell the web lane if longer phrases are expected.
9. **Kinship direction.** The web reads `GET /people/{ego}/kinship?to={alter}` as «alter es
   `label_es` de ego», which matches INT-API's «What `to` is to the person». The web shows the same
   «no relation» notice for `404 no_relation` and for `404 person_not_found`.
10. **No graph endpoint.** The tree walks one person at a time; the descendants view of a large
    family is about 40 to 80 requests.
    - Request, for a later wave: `GET /v1/people/{id}/tree?up=&down=` returning people (summary
      fields) and relationships in one response.
11. **The download's `content-disposition`.** The web passes the API's header through, or plain
    `attachment` when there is none.
    - Request: the API sets a filename with the right extension (`.gdz`, `.ged`, `.json`).
12. **Search.** The web passes `q` unchanged and relies on addendum C. The picker searches from
    2 characters with `limit=10`.

## Requests for other owners

- **`docs/ARCHITECTURE.md`** (coordinator). Add the addendum endpoints to the v1 table. Under
  Hosts, note that `/api/app/*` is the web's own route-handler prefix, app host only. Note that
  the web sets `proxyClientMaxBodySize` to 26 MB for imports.
- **`docs/HONEST_STATUS.md`.**
  - The tree view, the editors, the kinship lookup, import and export now exist in the web, and
    are not deployed.
  - Import and export are untested against the real API, because its jobs endpoints have not
    landed.
  - Editing places and visibility is not built.
- **The `README` and llms files** should not describe import or export as working until the API
  side lands.

## Known limits

- Events take no place yet: the API needs a `place_id`, and there is no place picker.
- `is_private` and `visibility` are displayed but not editable here.
- The spouse on a marriage event comes only from already-recorded partners.
- The person picker uses a server action, so searches are POSTs and Next runs them one after
  another; it is debounced by 300 ms.
