"""Domain integration and the Postgres job queue.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-01

- `person.search_text` becomes `search_tokens`: space-padded tokens folded by
  `domain.names.normalize_for_search` (services/search.py). The trigram index follows the column.
- `event.date_original` keeps the date text as the family typed it.
- `association` is reshaped to the GEDCOM 7 model: `person_id` is the associated person (the
  padrino, the witness) and the godchild is the event's principal, so the `associate_id` column
  goes; roles gain `officiant` and `other` (which needs a `phrase`).
- `job` is the queue table (docs/adr/0002-postgres-job-queue.md), under forced row-level
  security: a member inserts their own jobs and reads only their own; only a session that sets
  `app.job_runner = 'on'` (the worker) may read every queued job and update any of them.

No row existed in `association` before this revision (no endpoint wrote it), and the service had
not been deployed, so no data is rewritten. Downgrading empties `association` and `job`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_READ = (
    "family_space_id IN (SELECT m.family_space_id FROM space_member m"
    " WHERE m.user_sub = fh_current_user_sub()"
    " AND (fh_current_space_id() IS NULL OR m.family_space_id = fh_current_space_id()))"
)
_MEMBER_OF_CURRENT = (
    "family_space_id = fh_current_space_id() AND EXISTS (SELECT 1 FROM space_member m"
    " WHERE m.family_space_id = fh_current_space_id() AND m.user_sub = fh_current_user_sub())"
)
_JOB_POLICIES = ("fh_job_select", "fh_job_insert", "fh_job_update")


def upgrade() -> None:
    op.alter_column("person", "search_text", new_column_name="search_tokens")
    op.add_column("event", sa.Column("date_original", sa.String(length=200), nullable=True))
    _reshape_association()
    _create_job_table()
    _job_row_level_security()
    _ensure_trigram_index()


def downgrade() -> None:
    for policy in _JOB_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON job")
    op.drop_index("ix_job_creator", table_name="job")
    op.drop_index("ix_job_queue", table_name="job")
    op.drop_index(op.f("ix_job_family_space_id"), table_name="job")
    op.drop_table("job")
    op.execute("DROP FUNCTION IF EXISTS fh_job_runner()")

    op.execute("TRUNCATE association")
    op.drop_index("ix_association_person", table_name="association")
    op.drop_constraint(
        op.f("uq_association_event_id_person_id_role"), "association", type_="unique"
    )
    op.drop_constraint(op.f("ck_association_other_phrase"), "association", type_="check")
    op.drop_constraint(op.f("ck_association_role"), "association", type_="check")
    op.drop_column("association", "phrase")
    op.add_column("association", sa.Column("associate_id", sa.UUID(), nullable=False))
    op.create_check_constraint(
        op.f("ck_association_role"), "association", "role IN ('godparent', 'witness')"
    )
    op.create_check_constraint(
        op.f("ck_association_not_self"), "association", "person_id <> associate_id"
    )
    op.create_foreign_key(
        op.f("fk_association_family_space_id_associate_id_person"),
        "association",
        "person",
        ["family_space_id", "associate_id"],
        ["family_space_id", "id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        op.f("uq_association_event_id_person_id_associate_id_role"),
        "association",
        ["event_id", "person_id", "associate_id", "role"],
    )

    op.drop_column("event", "date_original")
    op.alter_column("person", "search_tokens", new_column_name="search_text")


def _reshape_association() -> None:
    op.drop_constraint(
        op.f("uq_association_event_id_person_id_associate_id_role"), "association", type_="unique"
    )
    op.drop_constraint(
        op.f("fk_association_family_space_id_associate_id_person"),
        "association",
        type_="foreignkey",
    )
    op.drop_constraint(op.f("ck_association_not_self"), "association", type_="check")
    op.drop_constraint(op.f("ck_association_role"), "association", type_="check")
    op.drop_column("association", "associate_id")
    op.add_column("association", sa.Column("phrase", sa.String(length=200), nullable=True))
    op.create_check_constraint(
        op.f("ck_association_role"),
        "association",
        "role IN ('godparent', 'witness', 'officiant', 'other')",
    )
    op.create_check_constraint(
        op.f("ck_association_other_phrase"), "association", "role <> 'other' OR phrase IS NOT NULL"
    )
    op.create_unique_constraint(
        op.f("uq_association_event_id_person_id_role"),
        "association",
        ["event_id", "person_id", "role"],
    )
    op.create_index(
        "ix_association_person", "association", ["family_space_id", "person_id"], unique=False
    )


def _create_job_table() -> None:
    op.create_table(
        "job",
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input", sa.LargeBinary(), nullable=True),
        sa.Column("result", sa.LargeBinary(), nullable=True),
        sa.Column("result_media_type", sa.String(length=100), nullable=True),
        sa.Column("result_filename", sa.String(length=200), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("family_space_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "input IS NULL OR octet_length(input) <= 26214400", name=op.f("ck_job_input_size")
        ),
        sa.CheckConstraint("kind IN ('gedcom_import', 'export')", name=op.f("ck_job_kind")),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')", name=op.f("ck_job_status")
        ),
        sa.ForeignKeyConstraint(
            ["family_space_id"],
            ["family_space.id"],
            name=op.f("fk_job_family_space_id_family_space"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
    )
    op.create_index(op.f("ix_job_family_space_id"), "job", ["family_space_id"], unique=False)
    op.create_index("ix_job_queue", "job", ["status", "created_at"], unique=False)
    op.create_index(
        "ix_job_creator", "job", ["family_space_id", "created_by", "created_at"], unique=False
    )


def _job_row_level_security() -> None:
    op.execute(
        "CREATE FUNCTION fh_job_runner() RETURNS boolean LANGUAGE sql STABLE AS "
        "$$ SELECT coalesce(current_setting('app.job_runner', true), '') = 'on' $$"
    )
    op.execute("ALTER TABLE job ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE job FORCE ROW LEVEL SECURITY")
    # A job is private to its creator: an export holds what *they* may see.
    op.execute(
        "CREATE POLICY fh_job_select ON job FOR SELECT USING ("
        f"fh_job_runner() OR (created_by = fh_current_user_sub() AND {_READ}))"
    )
    # Any member may submit (exports are free at every tier); the API gates imports by role.
    op.execute(
        "CREATE POLICY fh_job_insert ON job FOR INSERT WITH CHECK ("
        f"created_by = fh_current_user_sub() AND status = 'queued' AND {_MEMBER_OF_CURRENT})"
    )
    op.execute(
        "CREATE POLICY fh_job_update ON job FOR UPDATE "
        "USING (fh_job_runner()) WITH CHECK (fh_job_runner())"
    )


def _ensure_trigram_index() -> None:
    """Create the person trigram index when `pg_trgm` is installed but 0002 could not add it."""
    bind = op.get_bind()
    installed = bind.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
    ).scalar()
    if installed:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_person_search_trgm "
            "ON person USING gin (search_tokens gin_trgm_ops)"
        )
