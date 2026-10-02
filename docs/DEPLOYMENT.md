# Deployment

> Last Updated: 2026-10-02
>
> Boundary checkpoint (2026-10-01): public document. It describes how family-history is deployed through
> Enclii at the level a contributor needs. Operator procedures, cluster topology, secret paths beyond the
> names below, and break-glass steps live in the private internal-devops repository and are never copied
> here.

family-history runs on MADFAM's platform: Enclii (PaaS) on Kubernetes, with GitOps sync, a Cloudflare
tunnel as the only edge, Janua for identity and the platform's secret store. **Enclii first:** every
production action goes through Enclii's web UI, API or CLI.

## What gets deployed

| Workload | Image | Kubernetes | Public host |
|---|---|---|---|
| Web (Next.js, `apps/web`) | `ghcr.io/madfam-org/family-history-web` | Deployment and Service `family-history-web` (80 → 3000) | `fh.madfam.io` (landing), `fh-app.madfam.io` (app) |
| API (FastAPI, `api/`) | `ghcr.io/madfam-org/family-history-api` | Deployment and Service `family-history-api` (80 → 8000); Service `family-history-api-metrics` (9090) | `fh-api.madfam.io` |
| Worker (`python -m family_history.worker`) | the API image | Deployment `family-history-worker`; Service `family-history-worker-metrics` (9090) | none |
| Migrations | the API image | PreSync Job `family-history-migrate` | none |

The worker runs the API image with another command and reads its job queue from Postgres
([ADR 0002](./adr/0002-postgres-job-queue.md)). Build & Deploy therefore builds two images, and the
API's digest pin also moves the worker and the migrate hook.

Where each piece is declared:

- [`enclii.yaml`](../enclii.yaml): the project, the two services, their hosts, status-page entries and
  network intent.
- [`infra/k8s/production/`](../infra/k8s/production/): the kustomize base the GitOps sync applies: the
  Deployments, Services, the migrate hook, network policies, ExternalSecrets, the ServiceMonitor and the
  alerts.
- [`janua.client.yaml`](../janua.client.yaml): the Janua registrations (names only).
- [`.github/workflows/build-deploy.yml`](../.github/workflows/build-deploy.yml): builds, signs and pins the
  images.

Every container runs as uid 1001 with a read-only root filesystem and every capability dropped. Only
`/tmp` (and the web's `/app/.next/cache`) is writable. The namespace and the tunnel routes belong to the
platform; this repository never declares a Namespace or an Ingress.

## Build and pin

`.github/workflows/build-deploy.yml` calls Enclii's reusable `build-publish` workflow, pinned to the full
commit SHA of an Enclii release. For each service it builds the image, pushes it to GHCR as `:<commit>`,
signs it keylessly, verifies the signature, and commits the digest to
`infra/k8s/production/kustomization.yaml`. The GitOps sync then rolls it, and a lifecycle callback registers
the release with Enclii.

- The kustomization starts with all-zero placeholder digests. They never resolve, so nothing runs before
  the first real pin.
- The workflow is **dispatch-only** until the project is onboarded. It switches to push-on-main in its own
  pull request afterwards.
- It passes only named secrets: the org's Docker Hub pair and the repository's `ENCLII_CALLBACK_TOKEN`.

## Secrets

No secret value ever goes in a manifest, a commit, a pull request, a CI log or a chat. Production secrets
come from two places.

**The database URLs: the onboarding project Secret.** This follows the creator-census precedent.
`enclii onboard --secret-name family-history-secrets` writes the Kubernetes Secret
`family-history-secrets` with two keys:

- `DATABASE_URL`: pooled, through the platform's PgBouncer. The API reads it.
- `DIRECT_DATABASE_URL`: unpooled, straight to Postgres. Only the PreSync migrate Job reads it.

The operator builds both URLs from the same generated database password, which is never printed. The
Secret exists before the first sync, so the migrate hook never waits on an ExternalSecret. Both keys are
referenced one by one, so a missing key stops the pod visibly instead of booting it with an empty setting.
Never edit this Secret by hand.

**Everything else: `enclii secrets intake` and ExternalSecrets.** Values reach the store entry
`secret/family-history` only through the intake, and the ExternalSecrets read them by name. The intake
lowercases keys, so every property is lowercase.

| Kubernetes Secret | Key | Store property | Who provides it |
|---|---|---|---|
| `family-history-secrets` | `DATABASE_URL`, `DIRECT_DATABASE_URL` | none (not in the store) | `enclii onboard --secret-name family-history-secrets` |
| `family-history-api` | `FH_EARLY_ACCESS_ALLOWLIST` | `fh_early_access_allowlist` | Intake (who may use the app; empty lets nobody in) |
| `family-history-web` | `AUTH_JANUA_CLIENT_ID`, `AUTH_JANUA_CLIENT_SECRET` | `auth_janua_client_id`, `auth_janua_client_secret` | Enclii's OIDC provisioner, when it registers the `family-history-web` client |
| `family-history-web` | `FH_SESSION_SECRET` | `fh_session_secret` | Generated by the intake (32 bytes or more) |

The first deploy has no object-storage settings. Media lands in a later wave, and until then the API treats
`FH_S3_*` as optional.

Every mapped property must exist before the first sync. An ExternalSecret that maps a missing property
never becomes Ready, and the Deployments wait for it. `scripts/check-secret-coverage.py` keeps the manifests
in step with both sources:

- every reference is provisioned, by an ExternalSecret or by the onboarding Secret's two keys;
- every key is used;
- no sensitive variable is set as a plain value.

## First deploy

The platform operator runs these steps through Enclii. This repository is ready for them; the order
matters.

This repository requires every GitHub Action to be pinned to a full commit SHA, and GitHub applies that
requirement inside reusable workflows too. `.github/workflows/build-deploy.yml` therefore pins an Enclii
commit whose `build-publish.yml` pins every action by SHA. Keep it that way when bumping the pin (the
workflow's header says how).

1. **Onboard the project** from `enclii.yaml`, with `--secret-name family-history-secrets`. This creates the
   namespace with its platform labels, the managed database and its role, and the project Secret holding
   `DATABASE_URL` (pooled) and `DIRECT_DATABASE_URL` (direct). Then reconcile any service drift Enclii
   reports.
2. **Register the database role with the platform's connection pooler** (the platform's onboarding
   procedure). Until then the pooled `DATABASE_URL` is refused, and the API's `/ready` stays 503. The
   migrate hook still works, because it connects directly. The worker uses the same role through the
   pooler; if the platform admits pooler clients by pod label, it must also admit
   `app.kubernetes.io/name: family-history-worker`.
3. **Take the secrets in** (table above):
   - `fh_early_access_allowlist`, with at least one subject;
   - `fh_session_secret`, generated by the intake;
   - the web's Janua client, from Enclii's OIDC provisioner using the registration in
     `janua.client.yaml`: a confidential client with the exact redirect URI
     `https://fh-app.madfam.io/auth/callback`. The provisioner writes both `auth_janua_client_id` and
     `auth_janua_client_secret`.
4. **Grant the build what it needs:** the repository secret `ENCLII_CALLBACK_TOKEN`, and pull access for the
   cluster to the two GHCR packages.
5. **Dispatch Build & Deploy** with both services. Both digests are pinned on main, the migrate hook runs,
   and the pods roll.
6. **Wire the hosts.** Enclii provisions the three domains and their tunnel routes from `enclii.yaml`. Each
   route targets its Service on port 80; the network policies admit the tunnel to the web on 3000 and the
   API on 8000 only.
7. **Verify** each host ([RUNBOOK.md, Public hosts](./RUNBOOK.md#public-hosts)), then switch Build &
   Deploy to push-on-main in its own pull request.

## Migrations

`python -m family_history.cli migrate` (Alembic upgrade head over `DIRECT_DATABASE_URL`) is the only thing
that changes the schema. It runs as an ArgoCD PreSync hook, retried with a backoff so that a briefly
unreachable database does not fail the sync. Alembic's upgrade is transactional on Postgres, so a retry is
safe. Until the hook succeeds the API's `/ready` answers 503, and a failed hook blocks later syncs:
[RUNBOOK.md](./RUNBOOK.md#familyhistorymigrationfailed).

## Rollback

Roll back through Enclii: `enclii releases <service>` lists the releases, and `enclii rollback <service>
<v{n}>` returns to one. A migration is not rolled back by an image rollback; write migrations so the
previous image still runs against the new schema (expand first, contract in a later release).

## Checks that guard the deploy

CI (`.github/workflows/ci.yml`) renders the kustomize base and validates it. Its guards are:

- `scripts/check-manifests.py`: non-root, read-only root, every capability dropped, resources, probes,
  digest pins, tunnel and metrics reach, ExternalSecret shape, and a runbook anchor for every alert.
- `scripts/check-supply-chain.py`: workflows and Dockerfiles.
- `scripts/check-secret-coverage.py`: every secret reference is provisioned.
- `scripts/public-hygiene-check.sh`: nothing private in this public repository.
- The image-smoke job: each image is run under the same restrictions as the pods.
