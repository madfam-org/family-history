# ADR 0002 — A Postgres job queue instead of Celery and Redis

> Last Updated: 2026-10-01

- **Status:** Accepted for wave 2 (contract addendum E, INT-API lane). Replaces the Celery
  worker and `REDIS_URL` in `docs/ARCHITECTURE.md` §Contracts.
- **Context:** Imports and exports are the first background work. They are rare (a family
  imports a tree once and exports now and then), bounded (uploads are capped at 25 MiB) and
  private (a GEDCOM file holds a whole family, living people included). The platform had not
  provisioned Redis for this project, and every byte of family data already lives in one
  Postgres database under row-level security.

## Decision

1. **The queue is a table.** `job` is a tenant table under FORCE row-level security
   (migration `0003`):
   - columns: `id`, `family_space_id`, `kind` (`gedcom_import` | `export`), `status`
     (`queued` | `running` | `succeeded` | `failed`), `params` (jsonb), `input` (bytea,
     ≤ 25 MiB, checked by a constraint), `result` (bytea), `result_media_type`,
     `result_filename`, `report` (jsonb), `error_code`, `attempts`, `created_by`,
     `created_at`, `started_at`, `finished_at`, `expires_at` (finished + 24 h);
   - `gedcom_import` also covers native `family-history-tree/v1` imports (the kind names the
     queue lane, not the file format).
2. **Who sees what.** A member inserts only their own `queued` jobs, in a space they belong
   to (any role: the exit is free). A member reads only the jobs they created: an export
   holds what *its requester* may see, so nobody else may download it. Updates are refused to
   every session except the worker's, which sets the transaction-local `app.job_runner = 'on'`
   (function `fh_job_runner()`). No session may delete a job.
3. **The worker** is `python -m family_history.worker`, the API image with another command.
   - **Claim:** `UPDATE job SET status = 'running', ... WHERE id = (SELECT id FROM job WHERE
     status = 'queued' ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id`.
     Any number of workers can share the queue.
   - **Run:** one transaction per job, scoped to the job's creator (`app.user_sub`,
     `app.family_space_id`) plus `app.job_runner`. The import's rows and the job's final
     state commit together, so a crash never leaves half an import behind. The creator's
     role is checked again at run time (imports need editor or steward).
   - **Reclaim:** a job `running` longer than its 15-minute lease goes back to `queued`; at
     the third attempt it fails with `worker_timeout`.
   - **Purge:** `input` is dropped as soon as a job finishes; `result` is dropped once
     `expires_at` passes, and the download then answers `410 download_expired`.
   - **Liveness:** the loop touches `/tmp/worker-heartbeat`, and a side thread keeps
     touching it while a job runs within its lease. The pod's exec probe
     (`python -m family_history.worker healthcheck`) fails when the file is older than 120 s.
   - **Shutdown:** SIGTERM finishes the job in hand and exits; the pod's
     `terminationGracePeriodSeconds` (120) bounds it, and the lease covers anything longer.
   - **Configuration:** `DATABASE_URL` and `FH_ENV` only. Metrics (`fh_jobs_total`,
     `fh_job_duration_seconds`) use the same `:9090` listener rules as the API.
4. **Celery and Redis are removed**: the `celery[redis]` dependency, the `REDIS_URL` setting
   and the Celery worker command.

## Consequences

- `docs/ARCHITECTURE.md` §Contracts changes (the coordinator applies it):
  - Worker: `python -m family_history.worker` (was `celery -A family_history.worker:celery_app
    worker`).
  - Environment: `REDIS_URL` is gone; the worker reads `DATABASE_URL` and `FH_ENV`.
  - Shape diagram: `worker (Postgres queue)`.
- Postgres holds uploads and exports for at most a day after a job ends (bounded by the 25 MiB
  cap per job). Database backups therefore contain recent uploads; they are as private as the
  rest of the family data and share its retention.
- Throughput is "one job at a time per worker". That is enough for imports and exports; a
  heavier workload (media derivatives, OCR hand-offs) can add replicas without code changes,
  or revisit this decision.
- **Known limit:** `app.job_runner` is a capability flag, not an authentication. Any
  connection of the application role could set it; the protection is that no request path
  does. The stronger split, a separate database role for the worker, waits for the platform
  to provision a second role for the project. Until then the flag only widens access to the
  `job` table; tenant tables are still read and written under the creator's own scope.
- Media stays out of the queue. GEDZIP media entries are skipped, with a warning in the
  report, until the media bucket lands; results then may move to object storage.

## Alternatives considered

- **Celery with Redis** (the original plan): a second stateful service to operate, secure
  and back up, and a broker that would carry family files outside the RLS boundary.
- **A queue library over Postgres** (for example procrastinate): a new dependency that knows
  nothing about row-level security, for a loop that is under 300 lines here.
- **Object storage for inputs and results:** right for media, premature for a 25 MiB cap and
  a 24-hour life; it would add a credential to the worker for no gain today.
