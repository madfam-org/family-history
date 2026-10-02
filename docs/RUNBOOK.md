# Runbook

> Last Updated: 2026-10-01
>
> Boundary checkpoint (2026-10-01): public document. It covers what anyone operating family-history
> through Enclii needs: alert → symptom → first actions. Cluster topology, break-glass procedures and
> operator-only runbooks live in the private internal-devops repository and are never copied here.

## How to use this runbook

Every alert in `infra/k8s/production/prometheusrule.yaml` links to one section below, by anchor.
`scripts/check-manifests.py` fails the build when an alert points at a missing section.

**Enclii first.** Every action here goes through Enclii's web UI, API or CLI. Mutating `enclii ops`
verbs are a dry run until you add `--apply --reason "<ticket>"`; run the dry run first and read it.
Raw cluster access is not part of this runbook.

Commands you will use most:

| Need | Command |
|---|---|
| Sync and hook status of the app | `enclii ops apps status family-history --project family-history --json` |
| Why a pod is not ready | `enclii ops pods diagnose --project family-history` |
| Recent logs of a service | `enclii logs family-history-api` (or `family-history-web`) |
| Releases and rollback | `enclii releases family-history-api`, then `enclii rollback family-history-api <v{n}>` |
| Restart through a safe rollout | `enclii ops pods restart family-history-api --project family-history` |
| ExternalSecret readiness | `enclii ops secrets external family-history-api --project family-history` |

The contract paths: the API answers `/health` (liveness, no dependencies) and `/ready` (database and
migration head) on 8000, and `/metrics` on 9090 inside the cluster only; the web answers `/api/health` on
3000. Hosts: `fh.madfam.io`, `fh-app.madfam.io`, `fh-api.madfam.io`.

## Availability

### FamilyHistoryApiDown

**Symptom.** Prometheus cannot scrape the API's metrics listener for 5 minutes. The API is usually down
too: `https://fh-api.madfam.io/health` fails, and the app shows its error page.

**Actions.**
1. `enclii ops pods diagnose --project family-history`: look for probe failures, image pull errors,
   OOM kills and pending pods.
2. `enclii logs family-history-api`: a boot failure names the missing or invalid setting. In production
   the API refuses to start with `FH_AUTH_DISABLED` set, and with an empty required setting.
3. If a new release broke it, roll back: `enclii releases family-history-api`, then
   `enclii rollback family-history-api <previous v{n}>`.
4. If the app answers but the scrape does not, the metrics listener on 9090 died while uvicorn kept
   serving: restart through Enclii and open an issue on the API.

### FamilyHistoryApiMetricsAbsent

**Symptom.** No scrape target for the API has existed for 30 minutes.

**Actions.**
1. Check that the service has a release: `enclii releases family-history-api`. A service without an
   Enclii Release stays at zero replicas while the GitOps sync reports Synced. The Build & Deploy workflow
   registers releases through its lifecycle callback; a run that warned "No ENCLII_CALLBACK_TOKEN" did not.
2. Check the sync: `enclii ops apps status family-history --project family-history --json`. A failed
   migrate hook blocks every sync ([FamilyHistoryMigrationFailed](#familyhistorymigrationfailed)).
3. If pods are running, the ServiceMonitor no longer selects `family-history-api-metrics`: compare the
   labels in `infra/k8s/production/service-api-metrics.yaml` and `servicemonitor.yaml`.

### FamilyHistoryDeploymentUnavailable

**Symptom.** A deployment (`family-history-api` or `family-history-web`) has had no available replica
for 10 minutes. The matching host is down.

**Actions.**
1. `enclii ops pods diagnose --project family-history`.
2. API not ready but alive: `/ready` names the failing part.
   - `db`: Postgres or the pooler is unreachable or refused the role. Right after onboarding, the usual
     cause is a role the platform's connection pooler does not know yet ([DEPLOYMENT.md](./DEPLOYMENT.md#first-deploy),
     step 2). The direct URL still works then, so the migrate hook succeeds while `/ready` stays 503.
   - `migrations`: the schema is behind the image (see
     [FamilyHistoryMigrationFailed](#familyhistorymigrationfailed)).
3. Pods stuck creating with a config error: a referenced Secret key is missing. That is either
   `family-history-secrets` (written at onboarding) or an ExternalSecret that has not synced
   ([FamilyHistoryExternalSecretNotSynced](#familyhistoryexternalsecretnotsynced)).
4. Image pull errors: the digest in `infra/k8s/production/kustomization.yaml` must be one the Build &
   Deploy workflow pinned. The all-zero placeholder never resolves; dispatch the workflow.
5. Scaled to zero: see step 1 of [FamilyHistoryApiMetricsAbsent](#familyhistoryapimetricsabsent).

### FamilyHistoryPodCrashLooping

**Symptom.** A container restarted more than 3 times in 30 minutes.

**Actions.**
1. `enclii logs <service>` around the restarts, and `enclii ops pods diagnose --project family-history`
   for the last termination reason.
2. `OOMKilled`: see [FamilyHistoryMemoryNearLimit](#familyhistorymemorynearlimit).
3. Liveness failures: the API's `/health` and the web's `/api/health` must stay dependency-free. A
   liveness probe that checks the database turns a database blip into a restart loop.
4. A writing container on a read-only root filesystem fails on its first write: only `/tmp` (and the
   web's `/app/.next/cache`) are writable. Fix the image, never the security context.

## Delivery

### FamilyHistoryMigrationFailed

**Symptom.** The PreSync migrate Job (`family-history-migrate`) failed after its retries. Every later sync
of the app is blocked, so new images do not roll; the running pods keep serving.

**Actions.**
1. `enclii ops apps status family-history --project family-history --json`: the hook's phase and
   message.
2. `enclii ops pods logs family-history-migrate --project family-history`: the migration's own error (each
   attempt prints its exit code; the last line says when it gave up).
3. Connection errors on every attempt: `DIRECT_DATABASE_URL` in the onboarding project Secret
   `family-history-secrets` is wrong or the role lost access. That Secret belongs to Enclii's onboarding,
   never to a hand edit ([DEPLOYMENT.md](./DEPLOYMENT.md#secrets)); repair it through Enclii.
4. A migration error: fix the migration in a pull request. Never edit the schema by hand. The next sync
   re-runs the hook (the old Job is replaced before the new one is created).

### FamilyHistoryExternalSecretNotSynced

**Symptom.** `family-history-api` or `family-history-web` has not synced for 15 minutes. Running pods keep
their values; new pods of that workload may not start. The migrate hook does not depend on either.

**Actions.**
1. `enclii ops secrets external <name> --project family-history`: the failing key.
2. A mapped property is missing from the store: take it in through `enclii secrets intake submit`
   ([DEPLOYMENT.md](./DEPLOYMENT.md#secrets)). Properties are lowercase; an upper-case property never
   syncs.
3. After the intake reports ready: `enclii ops secrets refresh <name> --project family-history`.

## Capacity

### FamilyHistoryMemoryNearLimit

**Symptom.** A container has used more than 90% of its memory limit for 15 minutes.

**Actions.**
1. Look for a leak first: a steady climb after each deploy points at the code, a step after an import or
   export points at a job that belongs in the worker.
2. The cluster is tight. Raise a limit only in a pull request to the kustomize base, with the reason,
   and keep `enclii.yaml`'s `runtime.resources` in step.

## Public hosts

How to check each host by hand after a deploy:

| Host | Expect |
|---|---|
| `https://fh.madfam.io/api/health` | `200` |
| `https://fh.madfam.io/` | the public landing, `noindex` while `FH_INDEXABLE=false` |
| `https://fh-app.madfam.io/` | a redirect to Janua sign-in, then back to `/auth/callback` |
| `https://fh-api.madfam.io/health` | `200 {"status": "ok"}` |
| `https://fh-api.madfam.io/ready` | `200 {"status": "ready", ...}` |
| `https://fh-api.madfam.io/metrics` | not served (metrics never go through the tunnel) |
| `https://fh-api.madfam.io/v1/me` without a token | `401` |
