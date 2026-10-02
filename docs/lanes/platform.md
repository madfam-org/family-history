# Lane notes: platform (build, checks and deploy)

> Last Updated: 2026-10-01

Branch `feat/platform-deploy-and-ci`. This lane owns `enclii.yaml`, `janua.client.yaml`, `infra/**`,
`.github/**`, `scripts/**`, the root `.dockerignore`, `docs/DEPLOYMENT.md` and `docs/RUNBOOK.md`.

## What was built

- **CI** (`.github/workflows/ci.yml`). The three original jobs are unchanged: `api`, `web` and
  `agent-docs`. Added jobs:
  - `postgres`: Postgres 16 service, with tests run as a role that has neither SUPERUSER nor BYPASSRLS.
  - `quality-gates`: the org byte and size gates, with an empty size baseline.
  - `secrets`: gitleaks over the full history.
  - `security`: Trivy filesystem scan, pip-audit, pnpm audit, licences.
  - `guards`: every script and its tests, plus actionlint and shellcheck.
  - `contracts`: OpenAPI drift, once the command exists.
  - `manifests`: kustomize, kubeconform, the manifest rules and promtool.
  - `image-smoke`: each image that exists, run under the pod's restrictions.

  `codeql.yml` covers Python and JS/TS, each only when that language is present. `build-deploy.yml` is
  Enclii build-publish, pinned by SHA and dispatch-only.
- **Manifests**:
  - `enclii.yaml`: two services, three hosts, each domain pinned to port 80.
  - `infra/k8s/production/`: kustomize base with digest-pin placeholders.
  - `janua.client.yaml`: names only.
- **Guards** (`scripts/`), each with tests under `scripts/tests/` or a `--self-test`:
  - `check-supply-chain.py`
  - `check-manifests.py`
  - `check-secret-coverage.py`
  - `check-synthetic-fixtures.py`
  - `public-hygiene-check.sh`
  - `check-licenses.sh`
  - `ci/smoke-image.sh`

## Contracts this lane relies on

These are things other lanes must provide.

- **`postgres` CI job.** `FH_TEST_DATABASE_URL` is a non-superuser role (`fh_app`, NOBYPASSRLS) that owns
  the database `family_history_test`. `FH_TEST_ADMIN_DATABASE_URL` is the container superuser. Tests that
  need a real database carry `@pytest.mark.postgres`, and the marker should be registered in
  `api/pyproject.toml`.
- **API image.** Its default command serves the app on 8000 and starts metrics on 9090 in production. It
  sets a non-root `USER`. It must boot with `FH_ENV=test FH_AUTH_DISABLED=true` and nothing else, so that
  `/health` answers under `--read-only --tmpfs /tmp`. `python -m family_history.cli migrate` needs only
  `FH_ENV` and `DIRECT_DATABASE_URL`.
- **Web image.** `WORKDIR /app`, a non-root `USER`, and `/api/health` answering 200 under a read-only root
  with tmpfs `/tmp` and `/app/.next/cache`.
- **Dockerfiles.** Every `FROM` must be pinned by digest (`@sha256:`); `check-supply-chain.py` fails
  otherwise.
- **Synthetic lexicon.** `family_history.domain.synth.synthetic_lexicon()` may return strings or any
  nesting of mappings and iterables of strings. The name check skips with a notice until it exists.

## Secret map (first deploy)

There are two sources of secrets.

- **Store-held secrets.** These live at Vault path `secret/family-history`. They arrive only through
  `enclii secrets intake`, and the ExternalSecrets read them. The intake lowercases keys, so every
  property is lowercase. Each intake target must be registered in Enclii's intake registry, and the Vault
  writer must be allowed to write to `secret/family-history`.
- **Database URLs.** These follow the creator-census precedent. `enclii onboard --secret-name
  family-history-secrets --secrets-file <env>` writes them straight into a Kubernetes Secret; they are
  never in the store.

| Vault path | Intake target | ExternalSecret | K8s Secret | Property | Env var | Written by | Mounted by |
|---|---|---|---|---|---|---|---|
| `secret/family-history` | `family-history/api-access` | `family-history-api` | `family-history-api` | `fh_early_access_allowlist` | `FH_EARLY_ACCESS_ALLOWLIST` | operator intake (comma-separated Janua subjects or emails; not empty) | API Deployment |
| `secret/family-history` | `family-history/web-oidc` | `family-history-web` | `family-history-web` | `auth_janua_client_id` | `AUTH_JANUA_CLIENT_ID` | Enclii OIDC provisioner, `intake_key_map: {auth_janua_client_id: client_id}` | web Deployment (optional ref) |
| `secret/family-history` | `family-history/web-oidc` | `family-history-web` | `family-history-web` | `auth_janua_client_secret` | `AUTH_JANUA_CLIENT_SECRET` | Enclii OIDC provisioner, `intake_key_map: {auth_janua_client_secret: client_secret}` | web Deployment (optional ref) |
| `secret/family-history` | `family-history/web-session` | `family-history-web` | `family-history-web` | `fh_session_secret` | `FH_SESSION_SECRET` | `enclii secrets intake submit family-history/web-session --generate fh_session_secret` (32 bytes or more) | web Deployment (optional ref) |
| none (not in Vault) | none (onboarding) | none | `family-history-secrets` | none (key `DATABASE_URL`) | `DATABASE_URL` | `enclii onboard --secret-name family-history-secrets`: pooled URL through PgBouncer | API Deployment |
| none (not in Vault) | none (onboarding) | none | `family-history-secrets` | none (key `DIRECT_DATABASE_URL`) | `DIRECT_DATABASE_URL` | the same onboarding secrets file: direct URL to Postgres, same password | migrate Job (PreSync) only |

**Notes for the enclii lane:**

- **OIDC registry entry `family-history-web`** (`config/ecosystem-oidc-provision.yaml`):
  - `intake_target: family-history/web-oidc`;
  - both keys mapped in lowercase. Nauta's entry maps `client_id` the same way, and the client id stays
    out of this public repository;
  - `client_key: family-history-web`, `audience: family-history-api`, `is_confidential: true`;
  - one redirect, exactly `https://fh-app.madfam.io/auth/callback`. As registered there is no localhost
    callback, unlike the precedent: local development registers its own client;
  - allowed scopes exactly `openid profile email fh:read fh:write`, and grants `authorization_code`,
    `refresh_token`. `fh:export` and `fh:admin` are not granted to this client. The web also requests
    `offline_access`, an identity scope Janua grants on every sign-in;
  - no `session_intake_target`: re-minting the session secret on every provision run would sign everyone
    out.

  The external-secrets operator is all-or-nothing per ExternalSecret. A property whose name or case does
  not match syncs no key at all.
- **Database URLs.** The precedent's `DEPLOYMENT.md` "Going live" has the operator pass `--secret-name
  creator-census-secrets --secrets-file <env>` holding both URLs:
  - pooled: PgBouncer in the data namespace, port 6432;
  - direct: Postgres, port 5432;
  - both built from the same generated `--db-password`, never printed.

  Its runbook calls the same Secret "managed-Postgres addon" output. The Secret actually comes from the
  onboarding `--secret-name` and `--secrets-file` flags, not from `--db-name`, which creates the database
  and role only. The direct URL is not derived by the platform: the operator writes it into the same
  secrets file. family-history mirrors this exactly: same key names, pooled key on the API and direct key
  on the migrate Job only.
- **Not in the first deploy:** `FH_S3_*` (media is in the next wave; the API treats it as optional),
  `REDIS_URL` (no longer used: the worker's queue is in Postgres, ADR 0002) and `FH_SENTRY_DSN`.

## Operator steps (first deploy)

1. Done. Enclii main pins `build-publish.yml`'s actions by SHA, and `build-deploy.yml` pins that commit.
   Without it, GitHub refuses the run before any job starts.
2. `enclii onboard --repo madfam-org/family-history` with `--secret-name family-history-secrets --secrets-file
   <env>`. The env file carries `DATABASE_URL` (pooled through PgBouncer) and `DIRECT_DATABASE_URL`
   (direct), built from the generated `--db-password`, which is never printed. Then reconcile drift:
   `enclii services-sync --dir . --project family-history --dry-run`, then with `--reconcile-existing`.
3. Add the PgBouncer userlist line for the new role, following the platform procedure. Without it the
   pooled URL fails with "no such user" and `/ready` stays 503, while the migrate hook still succeeds.
4. Vault-writer policy for `secret/family-history`, and intake registry entries for
   `family-history/api-access`, `family-history/web-oidc` and `family-history/web-session`. The registry
   entries and the OIDC registration are merged in Enclii; the operator applies the writer policy.
5. Intake:
   - `enclii secrets intake submit family-history/api-access --reason "<ticket>"` (`fh_early_access_allowlist`);
   - `enclii secrets intake submit family-history/web-session --generate fh_session_secret --reason "<ticket>"`;
   - as a Janua admin: `enclii secrets provision oidc --platform family-history-web --registry
     config/ecosystem-oidc-provision.yaml --reason "<ticket>" --dry-run`, then the same without `--dry-run`.
     Pin the printed client id in the registry, never in this repository.
6. Repository secret `ENCLII_CALLBACK_TOKEN`, and cluster pull access (`ghcr-credentials`) for
   `ghcr.io/madfam-org/family-history-api` and `ghcr.io/madfam-org/family-history-web`.
7. Dispatch Build & Deploy (`services=family-history-api,family-history-web`). Then:
   - `enclii ops apps status family-history --project family-history --json`;
   - `enclii ops pods diagnose --project family-history`.
8. Domains:
   - `enclii projects environments family-history`;
   - `enclii ops domains reconcile family-history-web --apply --reason "<ticket>"`, and the same for
     `family-history-api`;
   - tunnel routes per the platform procedure, targets the two Services on port 80 (never 3000 or 8000).
9. Verify per `docs/RUNBOOK.md#public-hosts`, then open a PR switching Build & Deploy to push-on-main.

## Repository policy that shapes this lane

The repository requires every action to be pinned to a full commit SHA, and the policy also applies inside
called reusable workflows. This has two consequences:

- **Org quality gates.** `madfam-quality-gates.yml` uses tag-pinned actions, so the `quality-gates` job
  does not call it. Instead it runs the same gate scripts, from the same pinned commit of
  `madfam-org/.github`, through SHA-pinned actions. Switch back to `uses:` once the org workflow pins its
  actions.
- **Build & Deploy.** Enclii's `build-publish.yml` at `v1.0.0-alpha.14` used tag-pinned actions, which
  would have refused the first dispatch. Enclii main now pins them by SHA, and `build-deploy.yml` pins
  that main commit. Any later bump must keep every `uses:` in the called workflow SHA-pinned.

## How it was verified

Run locally before each push:

- `kustomize build` and `kubeconform -strict`;
- `actionlint` with shellcheck, and shellcheck on every script;
- every script against the repository, plus 45 unit tests and three self-tests;
- the licence gate and pip-audit against a real install of `api/`.
