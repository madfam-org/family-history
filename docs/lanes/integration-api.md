# Lane notes: API integration of the domain library and the GEDCOM engine

> Last Updated: 2026-10-01

Branch `feat/api-integration-domain-gedcom`, PR #17 (supersedes #11). Wave 2 lane INT-API wired
`family_history.domain` and `family_history.gedcom` into the API, following the wave-2 contract
addendum (sections A to F) shared with INT-WEB. This file is the input for the coordinator's
update of `docs/ARCHITECTURE.md`, `docs/HONEST_STATUS.md`, README and the llms files, which this
lane does not edit.

## What changed

| Area | Result |
|---|---|
| Event dates | `date_value` (GEDCOM 7, canonicalized) or `date_original` (es-MX text), bounds from the domain, `date_display {es, en}` |
| Living status | `domain.living.assess_living`, today in America/Mexico_City, recomputed after every write to events, participants or their citations; cited death evidence only |
| People | `is_private`, `display_name` (FORMAL) and `sort_name` (SORTING) from `domain.names.display_name` |
| Search | `normalize_for_search` + `given_name_variants`, ranked exact > variant > prefix over `person.search_tokens` |
| Kinship | `GET /v1/people/{id}/kinship?to=`, structured `domain.kinship.Kinship` with labels |
| Compadrazgo | `GET /v1/people/{id}/compadrazgo`, derived from godparent associations |
| Associations | `POST /v1/spaces/{id}/associations`, `DELETE /v1/associations/{id}`; events list them |
| Jobs | Postgres queue (ADR 0002), imports and exports, `GET /v1/jobs/{id}`, downloads |
| Interchange | Native `family-history-tree/v1` (lossless, JSON Schema), GEDCOM 7 / GEDZIP / 5.5.1 out, GEDCOM 7 / 5.5.1 / GEDZIP / native in |
| Worker | `python -m family_history.worker`, its Deployment, metrics Service, policies, Enclii doc |
| CLI | `seed-synth`, `validate-export`; `openapi` / `check-openapi` also cover the tree schema |
| Dependencies | `celery[redis]` and `REDIS_URL` removed; `tzdata` added |

## v1 endpoints (final list on this branch)

Scopes: GET needs `fh:read`; every other method needs `fh:write` (`fh:admin` implies both).
Creates answer `201`, job submissions `202`. Rows marked **new** or **changed** are this lane's.

| Method and path | Role | Returns |
|---|---|---|
| `GET /v1/me` | token only | `{sub, email, name, early_access, spaces}` |
| `GET /v1/spaces`, `POST /v1/spaces` | member / any | `[SpaceSummary]` / `201 Space` |
| `GET`, `PATCH /v1/spaces/{space_id}`; `GET /v1/spaces/{space_id}/members` | viewer / steward / viewer | `Space`; `[Member]` |
| `GET /v1/spaces/{space_id}/people?q=&limit=&cursor=` (**changed**: ranked search) | viewer | `{items: [PersonSummary], next_cursor}` |
| `POST /v1/spaces/{space_id}/people` | contributor | `201 Person` |
| `GET`, `PATCH`, `DELETE /v1/people/{person_id}` | viewer / editor / editor | `Person` / `Person` / `204` |
| `GET /v1/people/{person_id}/kinship?to={other_id}` (**new**) | viewer | `{kinship, label_es, label_en}`; `404 no_relation` |
| `GET /v1/people/{person_id}/compadrazgo` (**new**) | viewer | `{items: [CompadrazgoItem]}` |
| `POST /v1/spaces/{space_id}/relationships`; `DELETE /v1/relationships/{id}` | contributor / editor | `201 Relationship` / `204` |
| `POST /v1/spaces/{space_id}/events` (**changed**: dates) | contributor | `201 Event` |
| `PATCH`, `DELETE /v1/events/{event_id}` (**changed**: dates) | editor | `Event` / `204` |
| `POST /v1/spaces/{space_id}/associations` (**new**) | contributor | `201 Association` |
| `DELETE /v1/associations/{association_id}` (**new**) | editor | `204` |
| `POST`, `GET /v1/spaces/{space_id}/places` | contributor / viewer | `201 Place` / `[Place]` |
| `POST`, `GET /v1/spaces/{space_id}/sources`; `POST`, `GET /v1/sources/{id}/citations` | contributor / viewer | `201` / lists |
| `GET`, `POST /v1/spaces/{space_id}/assertions`; `POST /v1/assertions/{id}/status`, `/citations` | viewer / contributor (editor to accept) | as before; writes now recompute living status |
| `POST /v1/spaces/{space_id}/imports` (**new**) | editor, steward | `202 {job_id}` |
| `POST /v1/spaces/{space_id}/exports {format}` (**new**) | any member | `202 {job_id}` |
| `GET /v1/jobs/{job_id}` (**new**) | the job's creator | `Job` |
| `GET /v1/jobs/{job_id}/download` (**new**) | the job's creator | the file; `409 job_not_ready`, `410 download_expired` |
| `POST /v1/waitlist` | public | `202` |

## Shapes for INT-WEB

- **Event** adds `date_original: str | null`, `date_display: {es, en} | null`,
  `date_earliest`/`date_latest` (ISO dates, inclusive) and `associations: [EventAssociation]`.
  - `EventAssociation`: `{id, person_id, display_name, sex, role, phrase}`. `role` is
    `godparent | witness | officiant | other`.
  - Create/patch send `date_value` (GEDCOM 7 DateValue, any case or spacing; stored canonical)
    or `date_original` (≤ 200 characters, read by `parse_user_date_es`, then by the GEDCOM
    grammar), never both (`422 validation_error`). Patching either to `null` clears the date.
- **EventBrief** adds `date_display`.
- **PersonSummary** and **Person** add `sort_name` and `is_private`. `display_name` is now the
  FORMAL style: nombre de pila and surnames («María Guadalupe de la Garza Treviño»), no
  longer the nombre usado. `sort_name` is «Garza Treviño, María Guadalupe de la».
- **Kinship**: `{kinship: {kind, up, down, half, adoptive, partner_status, via}, label_es,
  label_en}`. `kind` is `self | partner | blood | foster | step | in_law`; `half` is null when
  unknown; `via` is a person id or null. `404 person_not_found` when `to` is not a person the
  caller can see in the same space, `404 no_relation` when unrelated within eight generations.
- **CompadrazgoItem**: `{person_id, display_name, relation, sacrament, label_es, label_en}`.
  `relation` is what that person is to this one: `godparent | godchild | compadre`;
  `sacrament` is `bautizo | confirmacion | primera_comunion | boda | xv_anos | presentacion`.
- **Association** (create): body `{event_id, person_id, role, phrase?}` (`other` needs a
  phrase), returns `{id, space_id, event_id, person_id, role, phrase, created_at}`.
  #2 had an unused `association` table with `person_id` + `associate_id`; migration 0003
  reshaped it to the GEDCOM 7 model: `person_id` is the associated person and the godchild is
  the event's principal (both spouses for a wedding).
- **Job**: `{id, kind: gedcom_import | export, status: queued | running | succeeded | failed,
  report, error_code, created_at, finished_at}`. Jobs are private to their creator.
- **Import report** (the GEDCOM engine's `ImportReport` shape):
  `{source_version, source_product, record_counts, created_records, diagnostics: [{severity,
  code, message, line}], extension_tags}`. `record_counts` counts the file's records by tag
  (`INDI`, `FAM`, ...; for a native file, by section); `created_records` counts the rows
  created (`people`, `places`, `sources`, `citations`, `events`, `unions`, `parent_child`,
  `assertions`). At most 500 diagnostics are listed, then one `info`
  `diagnostics_truncated`.
- **Export report**: `{format, record_counts, diagnostics}`.
- **Failed job report**: `{diagnostics: [{severity: "error", code, message, line: null}]}`, with
  `code` equal to `error_code`.
- **Uploads**: multipart field `file`; `.ged` (GEDCOM 7 or 5.5.1, detected from
  `HEAD.GEDC.VERS`), `.gdz` (media entries skipped with a warning) or `.json` (a native export;
  an addition to the addendum, needed for the round trip). 25 MiB, enforced by the API.
- **Downloads**: `Content-Disposition: attachment; filename="family-history-<YYYY-MM-DD>.ged"`
  (`.gdz`, `-gedcom551.ged`, `.json`); media types `text/vnd.familysearch.gedcom`,
  `application/vnd.familysearch.gedcom+zip`, `application/octet-stream` (5.5.1) and
  `application/json`.
- **Citing an event**: there is no event–citation table. Create an assertion `{subject_type:
  "event", subject_id, field: "occurred", value: true, citation_ids}`. A current assertion
  about a death, burial or cremation with at least one citation that is neither retracted nor
  disputed is the death evidence the living rule needs.

## Error codes added

| Code | Status | When |
|---|---|---|
| `invalid_date` | 422 | `date_value` is not GEDCOM 7, or `date_original` reads as nothing |
| `ambiguous_date` | 422 | `date_original` could mean two dates («1890-1895») |
| `no_relation` | 404 | kinship between unrelated people |
| `unknown_event` | 422 | association on an event the caller cannot see |
| `association_is_principal` | 422 | the person is the event's principal |
| `association_exists` | 409 | same event, person and role |
| `association_not_found` | 404 | delete of an unknown association |
| `unsupported_file` | 415 | upload extension or media type |
| `file_too_large` | 413 | upload over 25 MiB |
| `empty_file` | 422 | empty upload |
| `job_not_found` | 404 | not the caller's job |
| `job_not_ready` | 409 | download before the export succeeded |
| `no_download` | 409 | download of an import job |
| `download_expired` | 410 | 24 hours after the export finished |

**Job `error_code`s:** `gedcom_invalid` (not a GEDCOM dataset, or an unreadable GEDZIP),
`native_export_invalid` (a `.json` that is not a valid `family-history-tree/v1` export),
`insufficient_role` (the importer lost the editor role before the job ran), `not_a_member`
(the creator left the space), `invalid_format`, `worker_timeout` (three expired leases),
`internal_error`.

**Diagnostic codes** in import reports are stable strings:

- from the GEDCOM engine (kebab-case): `after-trlr`, `age-keyword`, `age-normalized`,
  `age-phrase`, `alia-text`, `ansel-decoded`, `ansel-replacements`, `asso-lifted`,
  `asso-no-role`, `banned-character`, `blank-line`, `blob-dropped`, `charset-fallback`,
  `charset-mismatch`, `charset-missing`, `charset-nonstandard`, `charset-unknown`,
  `conc-in-7`, `continuation-misplaced`, `continuation-of-pointer`, `continuation-orphan`,
  `coordinate`, `dangling-pointer`, `date-calendar`, `date-normalized`, `date-upgraded`,
  `duplicate-head`, `duplicate-xref`, `empty-line-value`, `enum-mapped`, `enum-other`,
  `event-text`, `exid`, `expected-pointer`, `file-path`, `gedc-version`,
  `gedzip-missing-media`, `gedzip-renamed`, `gedzip-unreferenced`, `head-dropped`,
  `inline-media`, `inline-source`, `invalid-encoding`, `language-unknown`, `level-jump`,
  `level-leading-zero`, `line-spacing`, `line-value-at`, `marked`, `media-type-unknown`,
  `media-without-file`, `medium-other`, `missing-head`, `missing-substructure`,
  `missing-trlr`, `not-allowed`, `not-utf8`, `note-record`, `orphan-line`, `payload-syntax`,
  `payload-y`, `pointer-type`, `resn-list`, `role-mapped`, `schema`, `schema-duplicate`,
  `sex-normalized`, `sex-unknown`, `sex-x`, `subn-dropped`, `submitter`, `tag-syntax`,
  `too-deep`, `too-many`, `trlr-content`, `type-added`, `undocumented-extensions`,
  `unexpected-payload`, `unexpected-pointer`, `unknown-record`, `unparseable-line`,
  `version`, `xref-length`, `xref-on-substructure`, `xref-renamed`, `xref-syntax`,
  `xref-void` (extracted from `family_history.gedcom`; that lane owns their meaning);
- from the importer (snake_case): `gedzip_media_skipped`, `media_skipped`,
  `person_without_name`, `structure_skipped`, `event_without_person`, `event_as_other`,
  `date_kept_as_text`, `sensitivity_narrowed`, `association_skipped`, `citation_skipped`,
  `pedigree_sealing`, `pedigree_other`, `diagnostics_truncated`;
- from the exporter: `event_without_principal`, `family_event_over_two`, plus the 5.5.1
  writer's own report codes.

## Semantics worth knowing

- **Living status:** `deceased` needs cited death evidence (above). An uncited death leaves a
  person born within 110 years `living`, which is the private side. `presumed_deceased` means
  every possible birth is older than 110 years.
- **Search:** `search_tokens` holds every name part folded by `normalize_for_search`
  (z→s, silent h, ll→y, …), space-padded. Each query word matches exactly (rank 0), through a
  hipocorístico (rank 1; «Chema» needs both «José» and «María»), or as a prefix (rank 2).
  Pages of a search carry a ranked cursor; a plain cursor sent with `q` is `400
  invalid_cursor`.
- **Export privacy:** an export holds what the requester can read through the API: private
  people only if they created them; sensitive events and assertions about people treated as
  living only if they recorded them; participants, associations and relationships only
  between exported people. No entitlement check: the exit is free at every tier.

## Native format `family-history-tree/v1`

- Pydantic models in `family_history/interchange/native.py`; the JSON Schema
  `packages/contracts/family-history-tree.v1.schema.json` is generated from them and checked
  for drift by `check-openapi` (CI's contracts job).
- Sections: `people` (P), `places` (L), `sources` (S), `citations` (C), `events` (E), `unions`
  (F), `parent_child` (R), `assertions` (A, current versions only). No database ids, users,
  timestamps or living status (derived).
- Ids come from a sort of each entity's exported content (`interchange/canonical.py`); exact
  ties fall back to row order, and imports create ids that keep file order
  (`persist.OrderedIds`). Hence export → import into an empty space → export is
  byte-identical; CI proves it for the native and the GEDCOM 7 formats.
- `python -m family_history.cli validate-export <file>` validates a file (schema plus
  references, acyclic places, subject types).

## GEDCOM mapping

| Model | GEDCOM 7 |
|---|---|
| Name form | `NAME` via `gedcom.mexico` (`GIVN`, `SURN` with `_FH_SURNAME_LINE`, `_FH_SURNAME_ORDER`, `NICK`); particles inside the surname piece; extra surnames as `SURN` + `_FH_SURNAME_LINE OTHER`; type as `TYPE` (`OTHER` + `PHRASE` for baptismal, religious, other) |
| Person | `INDI`, `SEX`, `RESN` (`CONFIDENTIAL` when treated as living, `PRIVACY` when private) |
| Couple / parents | `FAM` per union, per couple sharing a family event or a child, or per single parent; `PEDI` `ADOPTED`, `FOSTER`, `OTHER` + «Hijastro o hijastra» (step) |
| Union status | married: nothing; unión libre: `EVEN TYPE Unión libre` + `_FH_EVENT_KIND FREE_UNION`; divorced: the divorce event or `DIV Y`; partner, separated: not carried |
| Event | domain tag and `TYPE`; Mexican kinds through `gedcom.mexico.event_structure`; `DATE` + `PHRASE` (original text); `PLAC` (place path, leaf first); description as payload (OCCU, EDUC, RESI, EVEN) or `NOTE`; `CAUS` from a `cause_of_death` assertion |
| Participants, associations | `ASSO` + `ROLE` (`GODP`, `WITN`, `OFFICIATOR`, `PARENT`, `SPOU`, `OTHER` + `PHRASE`) |
| Citations | `SOUR @S@` + `PAGE` (page, foja, partida joined), `QUAY`, `DATA.TEXT`; event citations come from assertions about the event, person citations from assertions about the person |
| Sensitivity | `_FH_SENSITIVITY` (+ `RESN CONFIDENTIAL` when the subject may be living) |
| Source | `SOUR` + `TITL`, `REPO` record with `NAME` |

Not carried by GEDCOM (use the native format): name language, nombre usado, source type and
locator, place kinds and validity, union statuses partner and separated, assertion statuses
and assertions other than citations and causes of death. On import, files that are not ours
(`HEAD.SOUR` ≠ `FAMILY_HISTORY`) get the domain's default sensitivities (sacraments →
religion); places are rebuilt from `PLAC` paths (país, estado, municipio, localidad by depth).

## Worker and deployment

- `infra/k8s/production/deployment-worker.yaml`: API image, `python -m family_history.worker`,
  uid 1001, read-only root, `/tmp` emptyDir, ALL capabilities dropped, requests 50m / 192Mi,
  limits 500m / 768Mi, exec liveness and readiness (`healthcheck`, heartbeat ≤ 120 s),
  `terminationGracePeriodSeconds: 120`, `DATABASE_URL` from `family-history-secrets`.
- `service-worker-metrics.yaml` (9090, picked up by ServiceMonitor `family-history`),
  `allow-monitoring-ingress-worker`, `allow-worker-pgbouncer-egress` (data namespace, 6432
  only), kustomization resources; the API image entry pins the worker.
- `enclii.yaml`: `family-history-worker`, no domains, `status.enabled: false`.
- Local guard runs: `check-manifests.py` (23 objects) on an approximate render (no kustomize
  binary here), `check-secret-coverage.py`, the guards' 46 tests, `public-hygiene-check.sh`.
  kubeconform runs in CI only.

**Operator notes (first worker deploy):** the worker connects as the same database role as
the API, through PgBouncer, so the existing userlist line covers it. If the platform's data
namespace admits pooler clients by pod labels, it must also admit
`app.kubernetes.io/name: family-history-worker`. Build & Deploy still builds only
`family-history-api` and `family-history-web`; the worker runs the API image.

## Tests and verification

Local: ruff, mypy `--strict` (133 files) and pytest: **894 passed** with Postgres (domain and
GEDCOM suites included), of which 141 are API unit tests and 67 Postgres tests. Postgres ran on
PostgreSQL 14 (Homebrew, throwaway data directory, the suite's NOSUPERUSER NOBYPASSRLS role);
CI runs 16 with its split roles.

New tests:
- `tests/unit/test_dates_service.py`, `test_interchange.py` (GEDCOM 7 fixpoints for five
  seeds and every vendor fixture, strict 7.0 validity, native determinism under shuffled
  input, schema rejections, GEDZIP media, 5.5.1 re-import, mapping tables, ids, healthcheck);
- `tests/postgres/test_dates_search.py`, `test_kinship_flows.py`, `test_jobs_flows.py`
  (native and GEDCOM 7 round trips byte-identical through the API and the worker, GEDZIP and
  5.5.1, vendor imports with reports, upload rules, job privacy and expiry, export privacy,
  SKIP LOCKED, reclaim and timeout, the loop and its heartbeat, seed-synth refusing
  production).

## Deferred (for the ROADMAP)

- Media: GEDZIP media and `OBJE` records are skipped with warnings until the bucket lands.
- A separate database role for the worker (ADR 0002 known limit).
- A Prometheus alert on worker failures or a stale queue (needs a RUNBOOK anchor, which the
  platform lane owns).
- Peak memory of a 25 MiB import is unmeasured; the 768Mi limit is an estimate.
- Backfill of `search_tokens` for rows written before migration 0003 (none exist: the service
  was never deployed; any row gets tokens on its next names write).
- `GET /v1/people/{id}/tree?up=&down=` (INT-WEB's later-wave request).

## Contract requests for the coordinator

1. ARCHITECTURE §Contracts: Worker → `python -m family_history.worker` (ADR 0002); drop
   `REDIS_URL`; the worker reads `DATABASE_URL` and `FH_ENV`; the shape diagram's worker is a
   Postgres queue.
2. ARCHITECTURE v1 table: add the endpoints marked new above and the shape changes
   (`PersonSummary` gains `sort_name`, `is_private`; `living_status` includes
   `presumed_deceased`; `EventBrief` gains `date_display`).
3. HONEST_STATUS: GEDCOM 7 / 5.5.1 / GEDZIP import and export, the native export and the
   worker now exist; media inside GEDZIP does not.
4. `family_history.domain` docs say `has_evidence` should come from an accepted assertion;
   this lane counts any current cited assertion that is not retracted or disputed (the
   addendum's wording). Revisit if accepted-only is preferred.
