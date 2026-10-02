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

## Repository policy that shapes this lane

The repository requires every action to be pinned to a full commit SHA, and the policy also applies inside
called reusable workflows. This has two consequences:

- **Org quality gates.** `madfam-quality-gates.yml` uses tag-pinned actions, so the `quality-gates` job
  does not call it. Instead it runs the same gate scripts, from the same pinned commit of
  `madfam-org/.github`, through SHA-pinned actions. Switch back to `uses:` once the org workflow pins its
  actions.
- **Build & Deploy.** Enclii's `build-publish.yml`, both at `v1.0.0-alpha.14` and on enclii main, uses
  tag-pinned actions. The first dispatch will be refused until Enclii pins them, and the caller then bumps
  its SHA.

## How it was verified

Run locally before each push:

- `kustomize build` and `kubeconform -strict`;
- `actionlint` with shellcheck, and shellcheck on every script;
- every script against the repository, plus 43 unit tests and three self-tests;
- the licence gate and pip-audit against a real install of `api/`.
