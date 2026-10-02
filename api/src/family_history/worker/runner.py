"""The worker loop over the `job` table.

- Claim: `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`, so any number of
  workers share the queue without double work.
- Run: one transaction with the creator's RLS scope plus `app.job_runner`, so the import's rows
  and the job's final state commit together (a crash leaves the job `running`, never half done).
- Reclaim: a job `running` longer than the lease goes back to `queued`, or fails with
  `worker_timeout` after `max_attempts`.
- Purge: inputs and results are dropped once `expires_at` (finished + 24 h) has passed.
- Heartbeat: `/tmp/worker-heartbeat` is touched on every loop, and by a side thread while a job
  runs within its lease; the pod's exec liveness probe checks its age.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from prometheus_client import Counter, Histogram
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from family_history.auth import Principal
from family_history.db.engine import Database, set_scope
from family_history.metrics import REGISTRY
from family_history.models import Job, SpaceMember
from family_history.models.enums import JobKind, Role
from family_history.services.access import SpaceContext
from family_history.worker.handlers import JobFailure, Outcome, run_export, run_import

logger = logging.getLogger("family_history.worker")

JOBS = Counter(
    "fh_jobs_total", "Jobs finished, by kind and outcome.", ["kind", "outcome"], registry=REGISTRY
)
JOB_SECONDS = Histogram(
    "fh_job_duration_seconds", "Time to run a job.", ["kind"], registry=REGISTRY
)

_CLAIM = text(
    "UPDATE job SET status = 'running', started_at = now(), attempts = attempts + 1 "
    "WHERE id = (SELECT id FROM job WHERE status = 'queued' ORDER BY created_at, id "
    "FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING id"
)
_RECLAIM = text(
    "UPDATE job SET "
    "status = CASE WHEN attempts >= :max_attempts THEN 'failed' ELSE 'queued' END, "
    "error_code = CASE WHEN attempts >= :max_attempts THEN 'worker_timeout' ELSE error_code END, "
    "finished_at = CASE WHEN attempts >= :max_attempts THEN now() ELSE finished_at END, "
    "expires_at = CASE WHEN attempts >= :max_attempts THEN now() + :ttl ELSE expires_at END, "
    "input = CASE WHEN attempts >= :max_attempts THEN NULL ELSE input END "
    "WHERE status = 'running' AND started_at < now() - :lease RETURNING id"
)
_PURGE = text(
    "UPDATE job SET input = NULL, result = NULL "
    "WHERE expires_at < now() AND (input IS NOT NULL OR result IS NOT NULL) RETURNING id"
)


@dataclass(frozen=True)
class WorkerConfig:
    poll_seconds: float = 2.0
    lease: timedelta = timedelta(minutes=15)
    result_ttl: timedelta = timedelta(hours=24)
    max_attempts: int = 3
    heartbeat_path: Path = Path("/tmp/worker-heartbeat")  # noqa: S108 - an emptyDir in the pod
    heartbeat_seconds: float = 10.0


class Worker:
    def __init__(self, database: Database, config: WorkerConfig | None = None) -> None:
        self.database = database
        self.config = config or WorkerConfig()
        self._busy_since: float | None = None

    # -- heartbeat ---------------------------------------------------------------------------

    def beat(self) -> None:
        self.config.heartbeat_path.touch()

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        lease = self.config.lease.total_seconds()
        while not stop.wait(self.config.heartbeat_seconds):
            busy = self._busy_since
            if busy is not None and time.monotonic() - busy < lease:
                self.beat()

    # -- queue maintenance -------------------------------------------------------------------

    def _runner_session(self) -> Session:
        session = self.database.sessions()
        set_scope(session, user_sub=None, space_id=None, job_runner=True)
        return session

    def reclaim_stuck(self) -> list[uuid.UUID]:
        with self._runner_session() as session:
            ids = list(
                session.scalars(
                    _RECLAIM,
                    {
                        "max_attempts": self.config.max_attempts,
                        "lease": self.config.lease,
                        "ttl": self.config.result_ttl,
                    },
                ).all()
            )
            session.commit()
        for job_id in ids:
            logger.warning("job reclaimed", extra={"job_id": str(job_id)})
        return ids

    def purge_expired(self) -> int:
        with self._runner_session() as session:
            count = len(session.scalars(_PURGE).all())
            session.commit()
        return count

    def claim(self) -> uuid.UUID | None:
        with self._runner_session() as session:
            job_id: uuid.UUID | None = session.scalar(_CLAIM)
            session.commit()
        return job_id

    # -- running -----------------------------------------------------------------------------

    def run_once(self) -> bool:
        """Claim and run one job; False when the queue is empty."""
        self.reclaim_stuck()
        self.purge_expired()
        job_id = self.claim()
        if job_id is None:
            return False
        self._busy_since = time.monotonic()
        try:
            self.process(job_id)
        finally:
            self._busy_since = None
        return True

    def process(self, job_id: uuid.UUID) -> None:
        started = time.perf_counter()
        session = self.database.sessions()
        try:
            set_scope(session, user_sub=None, space_id=None, job_runner=True)
            job = session.get(Job, job_id)
            if job is None:
                return
            kind = job.kind
            ctx = self._context(session, job)
            try:
                outcome = self._run(ctx, job)
            except JobFailure as failure:
                session.rollback()
                self._finish_failed(job_id, failure.code, failure.message)
                JOBS.labels(kind=kind, outcome="failed").inc()
                return
            self._finish(session, job, outcome)
            session.commit()
            JOBS.labels(kind=kind, outcome="succeeded").inc()
            JOB_SECONDS.labels(kind=kind).observe(time.perf_counter() - started)
            logger.info("job succeeded", extra={"job_id": str(job_id), "kind": kind})
        except Exception:
            session.rollback()
            logger.exception("job crashed", extra={"job_id": str(job_id)})
            self._finish_failed(job_id, "internal_error", "The job failed unexpectedly.")
            JOBS.labels(kind="unknown", outcome="crashed").inc()
        finally:
            session.close()

    def _context(self, session: Session, job: Job) -> SpaceContext:
        """Scope the session to the job's creator and space, as the API would."""
        space_id, creator = job.family_space_id, job.created_by
        set_scope(session, user_sub=creator, space_id=space_id, job_runner=True)
        role = session.scalar(
            select(SpaceMember.role).where(
                SpaceMember.family_space_id == space_id, SpaceMember.user_sub == creator
            )
        )
        if role is None:
            raise JobFailure("not_a_member", "The job's creator no longer belongs to the space.")
        principal = Principal(sub=creator)
        return SpaceContext(db=session, principal=principal, space_id=space_id, role=Role(role))

    def _run(self, ctx: SpaceContext, job: Job) -> Outcome:
        if job.kind == JobKind.EXPORT.value:
            return run_export(ctx, job)
        return run_import(ctx, job)

    def _finish(self, session: Session, job: Job, outcome: Outcome) -> None:
        now = datetime.now(UTC)
        session.execute(
            text(
                "UPDATE job SET status = 'succeeded', report = CAST(:report AS jsonb), "
                "result = :result, result_media_type = :media_type, result_filename = :filename, "
                "input = NULL, error_code = NULL, finished_at = :now, expires_at = :expires "
                "WHERE id = :id"
            ),
            {
                "report": _json(outcome.report),
                "result": outcome.result,
                "media_type": outcome.media_type,
                "filename": outcome.filename,
                "now": now,
                "expires": now + self.config.result_ttl,
                "id": job.id,
            },
        )

    def _finish_failed(self, job_id: uuid.UUID, code: str, message: str) -> None:
        now = datetime.now(UTC)
        with self._runner_session() as session:
            session.execute(
                text(
                    "UPDATE job SET status = 'failed', error_code = :code, "
                    "report = CAST(:report AS jsonb), input = NULL, finished_at = :now, "
                    "expires_at = :expires WHERE id = :id"
                ),
                {
                    "code": code,
                    "report": _json(
                        {
                            "diagnostics": [
                                {
                                    "severity": "error",
                                    "code": code,
                                    "message": message,
                                    "line": None,
                                }
                            ]
                        }
                    ),
                    "now": now,
                    "expires": now + self.config.result_ttl,
                    "id": job_id,
                },
            )
            session.commit()

    def run_forever(self, stop: threading.Event) -> None:
        beat_stop = threading.Event()
        beater = threading.Thread(
            target=self._heartbeat_loop, args=(beat_stop,), name="heartbeat", daemon=True
        )
        beater.start()
        logger.info("worker started")
        try:
            while not stop.is_set():
                self.beat()
                try:
                    worked = self.run_once()
                except Exception:
                    logger.exception("worker loop error")
                    worked = False
                if not worked:
                    stop.wait(self.config.poll_seconds)
        finally:
            beat_stop.set()
            beater.join(timeout=5)
            logger.info("worker stopped")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
