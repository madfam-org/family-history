# Architecture and contracts

> Last Updated: 2026-10-01
>
> Boundary checkpoint (2026-10-01): public document. It names public hosts and ecosystem roles
> only. Topology, secret paths and runbooks live in the private internal-devops repository, per
> the repo-boundary contract.

## Shape

```
families ──▶ web (Next.js, one pod)          fh.madfam.io      public landing
                 │                            fh-app.madfam.io  signed-in app
                 │ server-side REST
                 ▼
             api (FastAPI) ──▶ Postgres (row-level security per family space)
                 │       └──▶ object storage (private bucket, presigned URLs)
                 ▼
             worker (Celery) ──▶ imports, exports, media derivatives, ecosystem calls
             mcp (generated from the API's OpenAPI; read-only tools first)
```

**Ecosystem seams.** These are consumed, never rebuilt (see [ECOSYSTEM.md](../ECOSYSTEM.md)):
- Janua: identity, organizations, entitlements and transactional email.
- Dhanam: billing.
- Selva: LLM work.
- tlacuilo: reading documents.
- ceq: generative media.
- PhyndCRM: waitlist consent.
- marca: QR codes.
- Angelia Courier: third-party messaging.
- Enclii: deploy.

## Contracts

These values are fixed. Changing any of them needs an ADR in [`docs/adr/`](./adr/).

### Runtime

| Item | Value |
|---|---|
| Python project | `api/`, distribution `family-history-api`, import root `family_history` at `api/src/family_history/` |
| API process | `uvicorn family_history.app:app --host 0.0.0.0 --port 8000` |
| Metrics | A separate listener on `:9090`, path `/metrics` (Prometheus text). Never routed through the tunnel |
| Liveness | `GET /health` → `200 {"status": "ok"}`. No dependency checks |
| Readiness | `GET /ready` → `200 {"status": "ready", "db": "ok", "migrations": "head"}`; otherwise `503` with the failing part named |
| Migrations | `python -m family_history.cli migrate`: Alembic upgrade head, using `DIRECT_DATABASE_URL` |
| OpenAPI | `python -m family_history.cli openapi` writes `packages/contracts/openapi.json`. CI fails on drift |
| Worker | `celery -A family_history.worker:celery_app worker` |
| MCP | `python -m family_history.mcp` (stdio) |
| Web | `apps/web`, package `@family-history/web`, Next.js **16.3.8** standalone on port `3000`. `GET /api/health` → `200` |
| Images | `ghcr.io/madfam-org/family-history-api` (api, worker, migrate, mcp) and `ghcr.io/madfam-org/family-history-web` |
| Dockerfiles | `api/Dockerfile` (context `api/`) and `apps/web/Dockerfile` (context: repo root, for the pnpm workspace) |
| Kubernetes | Namespace `family-history`.<br>Services: `family-history-web` (80 → 3000), `family-history-api` (80 → 8000), `family-history-api-metrics` (9090) |
| Hosts | `fh.madfam.io` (landing) and `fh-app.madfam.io` (app), both served by web; `fh-api.madfam.io` serves the API. Flat labels only, never `api.fh.madfam.io` |
| Containers | uid 1001, read-only root filesystem, every capability dropped |

### Environment

Variable names only; values never live in this repository.

| Process | Variable | Meaning |
|---|---|---|
| api | `FH_ENV` | `local`, `test`, `staging` or `production` |
| api | `DATABASE_URL`, `DIRECT_DATABASE_URL` | Pooled URL, plus the direct URL used for migrations |
| api | `REDIS_URL` | Queue for the worker |
| api | `FH_JANUA_ISSUER` | Default `https://auth.madfam.io` |
| api | `FH_JANUA_AUDIENCE` | `family-history-api` |
| api | `FH_JANUA_JWKS_URL` | Default `<issuer>/.well-known/jwks.json` |
| api | `FH_AUTH_DISABLED` | Honoured **only** when `FH_ENV` is `local` or `test`; boot fails otherwise |
| api | `FH_CORS_ORIGINS` | Comma-separated origins |
| api | `FH_EARLY_ACCESS_ALLOWLIST` | Comma-separated Janua subjects or emails. Empty means nobody is let in: fail closed |
| api | `FH_S3_ENDPOINT`, `FH_S3_BUCKET`, `FH_S3_ACCESS_KEY_ID`, `FH_S3_SECRET_ACCESS_KEY`, `FH_S3_REGION` | Private media bucket (S3-compatible) |
| api | `FH_SENTRY_DSN` | Optional |
| web | `FH_ENV` | As above |
| web | `AUTH_JANUA_ISSUER`, `AUTH_JANUA_CLIENT_ID`, `AUTH_JANUA_CLIENT_SECRET` | Ecosystem env contract for Next.js apps (ruling R45) |
| web | `FH_SESSION_SECRET` | 32 bytes or more. Signs and encrypts the app's own session cookie, never with the Janua secret (R42) |
| web | `FH_PUBLIC_LANDING_HOST`, `FH_PUBLIC_APP_HOST` | `fh.madfam.io` and `fh-app.madfam.io` |
| web | `FH_API_INTERNAL_URL` | Server-side API base, for example `http://family-history-api.family-history.svc.cluster.local` |
| web | `FH_INDEXABLE` | `false` on working hosts. Every page then carries `noindex`, and robots disallows all |
| web | `FH_PLAUSIBLE_DOMAIN` | Optional; analytics only through the self-hosted Plausible |

### v1 API used by the web app

The generated OpenAPI is the source of truth once the API ships. This table is the starting
contract both sides build against.

- **Auth.** Every `/v1/*` route except `POST /v1/waitlist` needs a Janua RS256 Bearer token with
  audience `family-history-api`.
- **Early access.** A subject outside `FH_EARLY_ACCESS_ALLOWLIST` gets `403` with code
  `early_access_required`.
- **Errors.** `{"error": {"code": "<snake_case>", "message": "<English>"}}`. The UI maps each code
  to Spanish copy.

| Method and path | Returns |
|---|---|
| `GET /v1/me` | `{sub, email, name, early_access: bool, spaces: [SpaceSummary]}` |
| `GET /v1/spaces` | `[SpaceSummary]` |
| `POST /v1/spaces {name}` | `Space`. The creator becomes `steward` |
| `GET /v1/spaces/{space_id}/people?q=&limit=&cursor=` | `{items: [PersonSummary], next_cursor}` |
| `POST /v1/spaces/{space_id}/people` | `Person` |
| `GET /v1/people/{person_id}` | `Person`: names, events, relationships, citations |
| `PATCH /v1/people/{person_id}` | `Person` |
| `POST /v1/spaces/{space_id}/relationships {type, from_person_id, to_person_id, qualifier}` | `Relationship` |
| `POST /v1/waitlist {email, locale, consent: true, aviso_version}` | `202`. Public and rate-limited |

**Shapes**

| Shape | Fields |
|---|---|
| `SpaceSummary` | `{id: uuid, name, role: steward\|editor\|contributor\|viewer, people_count}` |
| `PersonSummary` | `{id, display_name, sex: M\|F\|X\|U, living_status: living\|deceased\|unknown, birth: EventBrief\|null, death: EventBrief\|null, visibility: space\|private\|public_memorial}` |
| `EventBrief` | `{date_value: <GEDCOM 7 DateValue>\|null, place: str\|null}` |

## Data model

The model is a superset of GEDCOM 7.0.18.

| Entity | Notes |
|---|---|
| `FamilySpace` | Bound 1:1 to a Janua organization. The tenant for row-level security |
| `SpaceMember` | `steward`, `editor`, `contributor` or `viewer` |
| `Person` | Living status, evidence of death, visibility |
| `NameForm` | Ordered parts (given, apellido paterno, apellido materno, particles); nombre de pila vs nombre usado; apodos; per-language forms. No forced married name |
| `Relationship` | Parent–child with pedigree; unions (civil, religious, unión libre). Treated as a graph, not a tree |
| `Association` | Padrinos per sacrament, witnesses. Compadres are derived, never stored |
| `Event` and `Participant` | GEDCOM 7 date grammar; the original text is kept |
| `Place` | Time-aware hierarchy, keyed to INEGI where possible; parish and hacienda layers |
| `Source`, `Repository`, `Citation` | Typed: libro parroquial (libro, foja, partida), acta del Registro Civil, oral interview |
| `Assertion` | Append-only, with provenance. Status is suggested, accepted, disputed or retracted |
| `Media` | Original immutable; labelled derivatives |
| `Story`, `OralHistory` | Narrative and recorded memory |
| `Consent` | Per purpose, revocable |
| `Revision` | Every write |

See [PRIVACY.md](./PRIVACY.md) for the rules the model enforces.
