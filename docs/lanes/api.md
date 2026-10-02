# Lane notes: API service core

> Last Updated: 2026-10-01

Branch `feat/api-service-core`. This lane built the FastAPI service, its data model with
row-level security, the v1 routers, the CLI, the OpenAPI contract and the image. The pure
genealogy library (`family_history.domain`) and the GEDCOM engine are other lanes; this code
does not import them yet (see [Integration points](#integration-points)).

## Layout

| Path | What it holds |
|---|---|
| `api/src/family_history/app.py` | `create_app()`, the request middleware (request id, security headers, metrics, one redacted log line per request), lifespan, module-level `app` |
| `config.py` | pydantic-settings for every contract variable; boot guards |
| `auth.py` | Janua RS256 verification, the principal, early access, scopes |
| `errors.py` | The JSON error envelope and its handlers |
| `logging_setup.py` | JSON logs with redaction |
| `metrics.py` | Prometheus registry and the separate `:9090` listener |
| `db/engine.py`, `db/migrate.py` | Engine, sessions, RLS scope settings; Alembic helpers |
| `models/` | SQLAlchemy 2.0 typed models and the shared vocabularies (`models/enums.py`) |
| `migrations/versions/0001_*`, `0002_*` | Tables, then forced RLS and trigram indexes |
| `routers/`, `routers/schemas/` | v1 endpoints and their request/response shapes |
| `services/` | Access and roles, audit, names and search, privacy, pagination, events, evidence, rate limit |
| `cli.py`, `__main__.py` | `migrate`, `openapi`, `check-openapi` |
| `api/Dockerfile`, `api/.dockerignore` | The image |
| `api/scripts/lock.sh`, `api/requirements/` | Hashed locks (`runtime.txt`, `dev.txt`) |
| `api/tests/unit/`, `api/tests/postgres/` | Fast tests, and Postgres integration tests |

## Endpoints

Every `/v1` route except `GET /v1/me` and `POST /v1/waitlist` needs a Janua bearer token,
early access and the scope for its method: `fh:read` for GET, `fh:write` for anything else
(`fh:admin` implies both). Errors are `{"error": {"code", "message"}}`.

| Method and path | Role | Returns |
|---|---|---|
| `GET /health` | public | `200 {"status": "ok"}` |
| `GET /ready` | public | `200 {"status": "ready", "db": "ok", "migrations": "head"}`, or `503` naming the failing part (`db`: `unconfigured`/`unreachable`; `migrations`: `behind`/`unknown`) |
| `GET /v1/me` | token only | `{sub, email, name, early_access, spaces}`. No early access needed, so the app can show the waitlist state |
| `GET /v1/spaces` | member | `[SpaceSummary]` |
| `POST /v1/spaces {name}` | any | `201 Space`; the creator becomes `steward` |
| `GET /v1/spaces/{space_id}` | viewer | `Space` |
| `PATCH /v1/spaces/{space_id} {name}` | steward | `Space` (rename) |
| `GET /v1/spaces/{space_id}/members` | viewer | `[{user_sub, role, created_at}]` |
| `GET /v1/spaces/{space_id}/people?q=&limit=&cursor=` | viewer | `{items: [PersonSummary], next_cursor}`, ordered by surname |
| `POST /v1/spaces/{space_id}/people {sex, visibility, names[]}` | contributor | `201 Person` |
| `GET /v1/people/{person_id}` | viewer | `Person`: names, events, relationships, citations |
| `PATCH /v1/people/{person_id} {sex?, visibility?, names?}` | editor | `Person`; `names` replaces every name form |
| `DELETE /v1/people/{person_id}` | editor | `204`; soft delete recorded in `revision` |
| `POST /v1/spaces/{space_id}/relationships {type, from_person_id, to_person_id, qualifier}` | contributor | `201 Relationship` |
| `DELETE /v1/relationships/{relationship_id}` | editor | `204` |
| `POST /v1/spaces/{space_id}/events {type, date_value?, place_id?, description?, sensitivity?, participants[]}` | contributor | `201 Event` |
| `PATCH /v1/events/{event_id}` | editor | `Event` |
| `DELETE /v1/events/{event_id}` | editor | `204` |
| `POST /v1/spaces/{space_id}/places` | contributor | `201 Place` |
| `GET /v1/spaces/{space_id}/places?q=&kind=&parent_id=&limit=` | viewer | `[Place]` |
| `POST /v1/spaces/{space_id}/sources` | contributor | `201 Source` |
| `GET /v1/spaces/{space_id}/sources?q=&limit=` | viewer | `[Source]` |
| `POST /v1/sources/{source_id}/citations` | contributor | `201 Citation` (libro/foja/partida, quality 0–3) |
| `GET /v1/sources/{source_id}/citations` | viewer | `[Citation]` |
| `GET /v1/spaces/{space_id}/assertions?subject_type=&subject_id=&include_history=` | viewer | `[Assertion]`, current versions unless `include_history` |
| `POST /v1/spaces/{space_id}/assertions` | contributor (`suggested`); editor (`accepted`/`disputed`) | `201 Assertion` |
| `POST /v1/assertions/{assertion_id}/status {status, citation_ids?}` | editor; the author may retract their own | `201 Assertion` (a new version) |
| `POST /v1/assertions/{assertion_id}/citations {citation_ids}` | contributor | `201 Assertion` (a new version) |
| `POST /v1/waitlist {email, locale, consent, aviso_version}` | public | `202 {"status": "accepted"}` |

**Vocabulary** (aligned with `family_history.domain`, mirrored in `models/enums.py`):
- `relationship.qualifier` is the pedigree for `parent_child` (`birth`, `adopted`, `foster`,
  `step`; `from_person_id` is the parent). For `union` it is the partner status (`married`,
  `union_libre`, `partner`, `separated`, `divorced`). Storage uses two columns, `pedigree` and
  `partner_status`. Civil and religious marriages are events (`civil_marriage`,
  `religious_marriage`).
- `living_status` is one of `living`, `deceased`, `presumed_deceased` or `unknown`. It is
  derived from events, never input. `deceased` needs a death, burial or cremation event.
  `presumed_deceased` means a birth bound more than 110 years ago. `unknown` means no birth
  bound. `living` and `unknown` are both treated as living.
- `event.type` is a `domain.events.EventType` code. `date_value` is GEDCOM 7 DateValue text
  (uppercase tokens). `date_earliest` and `date_latest` stay null until the domain library fills
  them.

**Rules the API enforces:**
- A person who may be living cannot be `public_memorial` (`living_person_not_public`). If a
  death event is deleted, a public person goes back to `space` visibility.
- `private` people are visible only to their creator, in lists, details, counts and
  relationship ends.
- Sacramental events (baptism, christening, confirmation, first communion, religious marriage)
  default to the `religion` sensitivity. Assertion fields `cause_of_death` and `medical_note`
  default to `health`. `religious_affiliation`, `ethnic_origin` and `political_affiliation`
  default to their own classes.
- **Sensitive facts about people treated as living are visible only to whoever recorded
  them.** This covers events and assertions with a sensitivity class. It is a holding rule until
  consent flows exist (PRIVACY.md §3): other members, editors and stewards included, do not see
  them.
- Assertions are append-only. A status change or a citation link writes a new row with
  `supersedes_id`. The database grants only SELECT and INSERT on `assertion` and `revision`.
  Accepting needs at least one citation (`citation_required`). Acting on an old version returns
  `assertion_superseded`.
- Every write adds a `revision` row: actor, entity, action and a JSON diff.

**Stable error codes:**
- Auth: `missing_token`, `invalid_token`, `token_expired`, `auth_unavailable`,
  `early_access_required`, `insufficient_scope`, `insufficient_role`.
- Not found: `space_not_found`, `person_not_found`, `event_not_found`, `relationship_not_found`,
  `source_not_found`, `assertion_not_found`, `not_found`.
- Input: `validation_error`, `invalid_cursor`, `unknown_person`, `unknown_place`,
  `unknown_subject`, `unknown_citation`, `multiple_primary_names`, `living_person_not_public`,
  `relationship_exists`, `invalid_status`, `citation_required`, `assertion_superseded`,
  `consent_required`.
- Platform: `rate_limited`, `database_unavailable`, `method_not_allowed`, `internal_error`.

Validation messages name the failing fields and never echo input values.

## Row-level security design

Two transaction-local settings drive every policy: `app.user_sub` and `app.family_space_id`.
They are set with `set_config(..., true)`, so they never outlive the transaction and are safe
behind a transaction-pooling proxy. `db/engine.py` keeps them in `Session.info`, and an
`after_begin` hook re-applies them to every transaction the session opens, including the one
after a commit.

The request flow is defence in depth:
1. Authenticate the caller, then set `app.user_sub`.
2. Check membership and role in the application (`services/access.py`). An absent membership
   returns 404 so a space's existence never leaks.
3. Only then set `app.family_space_id`.

Migration `0002` FORCEs RLS on every table, so the table owner is bound too; only superuser and
BYPASSRLS roles skip it.

| Table(s) | SELECT | INSERT | UPDATE / DELETE |
|---|---|---|---|
| Tenant tables (`person`, `name_form`, `relationship`, `place`, `event`, `event_participant`, `association`, `source`, `citation`) | rows in spaces where `app.user_sub` is a member, narrowed to `app.family_space_id` when set | `family_space_id = app.family_space_id` and the caller is a non-viewer member there | same as INSERT |
| `assertion`, `revision` | as tenant | as tenant | none (append-only) |
| `space_member` | own rows, or rows of `app.family_space_id` | `family_space_id = app.family_space_id` | same |
| `family_space` | spaces where `app.user_sub` is a member | `created_by = app.user_sub` | UPDATE by a steward of `app.family_space_id`; no DELETE |
| `waitlist_entry` | only with `app.waitlist_relay = 'on'` (the future PhyndCRM relay) | anyone | relay only |

Membership is checked inside the tenant policies through a sub-select on `space_member`. A
caller who points `app.family_space_id` at a space they do not belong to sees nothing and
writes nothing. Viewers cannot write even if the application's role check were bypassed.

Known limit: a Postgres policy cannot read its own table (that is infinite recursion). So
`space_member` writes, and reads of other members, key on the space setting rather than on a
membership sub-select. The application sets that setting only after it has checked
membership: as a steward for writes, or while creating the space.

Composite foreign keys `(family_space_id, x_id)` stop a row from referencing a person, event,
place or source in another space. Foreign-key checks bypass RLS, so this matters.

Ids are generated by the application. Inserts therefore skip `RETURNING`, which RLS would
otherwise check against SELECT policies before the creator's membership row exists.

**Roles.** In production, the API connects as a non-superuser role without BYPASSRLS; it may own
the tables, because RLS is forced. The tests connect as such a role so RLS actually applies (see
below). `pg_trgm` is optional: `0002` creates it in a savepoint when allowed and adds GIN
trigram indexes on `person.search_text` and `place.search_text`.

## Search

The search is portable. The API maintains `person.search_text`: every part of every name form,
plus nicknames and particles, lowercased with accents stripped. Query tokens are normalized the
same way and matched with escaped `LIKE '%token%'`, all tokens required. It does not depend on
`unaccent`. The trigram index speeds it up where present. Lists page by a keyset cursor on
`(sort_name, id)`, where `sort_name` is surnames then given names, normalized.

## Environment used

- `FH_ENV`: default `production` when unset, which is the safe side.
- `DATABASE_URL`: when unset, `/ready` reports `db: unconfigured` and data routes return `503`.
- `DIRECT_DATABASE_URL`: used only by `cli migrate`, which needs nothing else.
- `FH_JANUA_ISSUER`, `FH_JANUA_AUDIENCE`, `FH_JANUA_JWKS_URL`: JWKS cache of 300 s, 5 s fetch
  timeout, 30 s leeway.
- `FH_AUTH_DISABLED`: boot fails outside `local`/`test`.
- `FH_CORS_ORIGINS`
- `FH_EARLY_ACCESS_ALLOWLIST`: case-insensitive; empty means nobody.
- `FH_METRICS_PORT`: **not in the contract table yet**. Unset means 9090 in staging and
  production and off in local and test; `0` or empty means off.
- `FH_S3_*`: optional; nothing reads them at boot.
- `FH_SENTRY_DSN`: parsed but not wired, because there is no Sentry SDK dependency.
- `REDIS_URL`: parsed; the worker lane uses it.

The first deploy needs only `DATABASE_URL`, `DIRECT_DATABASE_URL` and
`FH_EARLY_ACCESS_ALLOWLIST` (plus non-secret `FH_ENV`).

## Logs and metrics

- **Logs.** One JSON object per line.
  - Extra keys that look personal (`name`, `email`, `token`, `authorization`, `password`,
    `secret`, `cookie`, `ip`, ...) become `[redacted]`.
  - Messages and string values are scrubbed of emails, bearer tokens and JWTs.
  - The request line logs the route template, never the path or the query string.
  - Uvicorn's access log is disabled. httpx and alembic are raised to WARNING.
- **Metrics.** `fh_http_request_duration_seconds` and `fh_http_requests_total`, labelled by
  method, route template and status, plus `fh_auth_failures_total{code}` and
  `fh_waitlist_requests_total{outcome}`. They are served only on the separate listener.

## Waitlist

- The email is validated without new dependencies. Its domain is lowercased, and a unique index
  on `lower(email)` prevents duplicates.
- `INSERT ... ON CONFLICT DO NOTHING` always answers `202`, so a caller cannot learn whether an
  email is already on the list.
- Consent must be true (`consent_required`), and `aviso_version` is stored with `consent_at`.
- Rate limit: 5 requests per 10 minutes per hashed address, in process. Over the limit the API
  answers `429 rate_limited` with `Retry-After`.
- The address is `CF-Connecting-IP` when present (the Cloudflare edge overwrites it), otherwise
  the socket peer. It is hashed with SHA-256 and a random per-process salt and stored as
  `ip_hash`, so it is not linkable across restarts.

## How to run

```bash
cd api
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e '.[dev]'
.venv/bin/ruff check . && .venv/bin/mypy src && .venv/bin/pytest -q

# Postgres suite against a throwaway container (superuser URL: the suite creates its own
# non-superuser role and database, migrates as that role and drops both at the end)
docker run -d --name fh-api-pg -e POSTGRES_PASSWORD=local-dev-only -e POSTGRES_USER=fh \
  -e POSTGRES_DB=fh -p 5544:5432 postgres:16-alpine
FH_TEST_DATABASE_URL=postgresql://fh:local-dev-only@127.0.0.1:5544/fh .venv/bin/pytest -q
docker rm -f fh-api-pg

# Local server
FH_ENV=local FH_AUTH_DISABLED=true DATABASE_URL=... .venv/bin/uvicorn family_history.app:app
DIRECT_DATABASE_URL=... .venv/bin/python -m family_history.cli migrate
.venv/bin/python -m family_history.cli openapi        # rewrite packages/contracts/openapi.json
.venv/bin/python -m family_history.cli check-openapi  # exit 1 on drift
api/scripts/lock.sh                                   # after any dependency change
```

**Test databases.**
- `FH_TEST_DATABASE_URL` as a superuser, or as a role with CREATEROLE and CREATEDB: the suite
  creates role `fh_rls_app` (NOSUPERUSER NOBYPASSRLS) and a fresh database that role owns.
- As a non-privileged role (CI's split): the suite uses it as-is and fails loudly if it bypasses
  RLS. When `FH_TEST_ADMIN_DATABASE_URL` is set, that superuser installs `pg_trgm` first, and the
  downgrade round-trip test runs because CI's database is throwaway.
- Tables are truncated after each test.

## Tests

- **Unit** (no database): 101, plus the scaffold's package test. They cover:
  - settings guards;
  - JWT checks: valid, expired, wrong `aud`/`iss`, missing claims, foreign key, unknown `kid`,
    HS256 key confusion, `alg=none`, malformed tokens, JWKS caching;
  - early access by subject or verified email, the empty allowlist, the synthetic principal,
    scopes;
  - the error envelope, request ids, security headers, HSTS, CORS, docs off outside dev;
  - the metrics listener and lifespan, log redaction;
  - names and search normalization, living-status rules, sensitivity defaults, cursors, the
    rate limiter;
  - schema validation, OpenAPI drift and the CLI.
- **Postgres** (`@pytest.mark.postgres`, runs only with `FH_TEST_DATABASE_URL`): 44.
  - RLS: forced on all 14 tables; raw selects see nothing unscoped or in another space; inserts
    into another space fail; cross-space updates and deletes touch nothing; viewers cannot
    write; revisions are append-only; only stewards rename; the waitlist is insert-only.
  - Migrations: at head; models match migrations (autogenerate is empty); downgrade and upgrade
    round-trip; readiness.
  - CRUD flows: spaces, people, search with accents, pagination, relationships, cross-space
    references, events and living status, sacrament sensitivity, private people, role gates,
    sources, citations, the assertion lifecycle, sensitive assertions.
  - Waitlist: accepted, duplicate indistinguishable, consent, validation, rate limit, the email
    never logged.

## Integration points

These are for the coordinator.
- `models/enums.py` mirrors `domain.events.EventType`, `domain.kinship.Pedigree` and
  `PartnerStatus`, and `domain.living.LivingStatus`. Once `family_history.domain` is on `main`,
  import those enums there and delete the copies. The string values are identical, so no data
  changes.
- `services/privacy.compute_living_status` mirrors `domain.living` for the event-only case.
  Swap it for `domain.living.assess_living` when the domain fills `date_earliest` and
  `date_latest` from `date_value`. `services/events.recompute_living` is the one call site.
- `services/names` (normalization, display, sort key) can be replaced by `domain.names` where
  the two agree; `person.search_text` and `person.sort_name` are rebuilt on every names write.
- `date_value` is validated only for shape (uppercase GEDCOM tokens). Parse it with
  `domain.dates` at integration.

## Contract requests

1. **`FH_METRICS_PORT`** is not in ARCHITECTURE.md §Environment. Please add it: unset means
   9090 in staging and production and off in local and test.
2. **`living_status`** gains `presumed_deceased` (coordinator note 2). `PersonSummary` in
   ARCHITECTURE.md still lists `living|deceased|unknown`.
3. **`POST` status codes.** Creates return `201` (spaces, people, relationships, events, places,
   sources, citations, assertions). Assertion status changes and citation links return `201`
   because they create a new version. The contract table names only the shape.
4. **`/v1/me` is reachable without early access** (it reports `early_access: false` and no
   spaces), so the web app can show the waitlist state. Every other `/v1` route returns
   `early_access_required`.
5. **The relationship `qualifier` stays one field**, as in the contract. Its meaning depends on
   `type`: the pedigree or the partner status. The old `status` field is gone.
6. **Membership management** (invite, change role, remove) has no endpoint. It needs the Janua
   organization binding (`family_space.janua_organization_id` exists but nothing sets it).
7. **A stable IP-hash salt** (a variable such as `FH_IP_HASH_SALT`) would make `ip_hash`
   comparable across restarts and replicas. Today the salt is random per process. The rate
   limiter is in process, which is right for one replica only.
8. **`FH_SENTRY_DSN`** needs the `sentry-sdk` dependency before it does anything. It was not
   added because it is not essential to M1.

## Verification and caveats

- ruff, mypy `--strict` and pytest pass locally: 101 unit and 44 Postgres tests. The Postgres
  tests also passed under a simulated CI split, with a NOSUPERUSER NOBYPASSRLS owner role plus
  a superuser admin URL.
- The Postgres tests ran on **PostgreSQL 14** (Homebrew binaries in a throwaway data directory),
  not 16. The local Docker daemon hung on every container create and build, for this lane and
  others on the machine.
- **The image was not built locally**, for the same reason. What was checked instead:
  - every pin in `requirements/runtime.txt` resolves to a linux/amd64 cp312 wheel whose hash
    matches (`pip download --require-hashes --only-binary=:all:`);
  - the app boots with only `FH_ENV=test FH_AUTH_DISABLED=true` (`/health` 200, `/ready` 503
    `unconfigured`).

  CI's image build is the first real build.
- The Dockerfile pins `python:3.12-slim` by its multi-arch index digest (2026-10-01).
