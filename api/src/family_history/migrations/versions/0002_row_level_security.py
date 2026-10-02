"""Forced row-level security and search indexes.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-01

- Tenant tables (everything carrying `family_space_id`) are readable only for spaces where
  `app.user_sub` is a member, narrowed to `app.family_space_id` when that is set. Writes need
  `app.family_space_id` set and a non-viewer membership in it. `assertion` and `revision` are
  append-only: they have SELECT and INSERT policies and nothing else.
- `space_member` and `family_space` reads are keyed on `app.user_sub`.
- `waitlist_entry` is insert-only for the API; reading needs `app.waitlist_relay = 'on'`.

RLS is FORCEd, so it binds the table owner too; only superusers and BYPASSRLS roles skip it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_rls_functions()
    _enable_row_level_security()
    _add_trigram_indexes()


def downgrade() -> None:
    # Policies reference space_member, so they go before any table does.
    for table, policies in _POLICIES.items():
        for policy in policies:
            op.execute(f"DROP POLICY IF EXISTS {policy} ON {table}")
    op.execute("DROP INDEX IF EXISTS ix_person_search_trgm")
    op.execute("DROP INDEX IF EXISTS ix_place_search_trgm")
    for table in (*TENANT_TABLES, "space_member", "family_space", "waitlist_entry"):
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS fh_current_space_id()")
    op.execute("DROP FUNCTION IF EXISTS fh_current_user_sub()")


TENANT_TABLES = (
    "person",
    "name_form",
    "relationship",
    "place",
    "event",
    "event_participant",
    "association",
    "source",
    "citation",
    "assertion",
    "revision",
)
APPEND_ONLY_TABLES = frozenset({"assertion", "revision"})
_TENANT_POLICIES = ("fh_tenant_select", "fh_tenant_insert", "fh_tenant_update", "fh_tenant_delete")
_POLICIES: dict[str, tuple[str, ...]] = {
    **{table: _TENANT_POLICIES for table in TENANT_TABLES},
    "space_member": (
        "fh_member_select",
        "fh_member_insert",
        "fh_member_update",
        "fh_member_delete",
    ),
    "family_space": ("fh_space_select", "fh_space_insert", "fh_space_update"),
    "waitlist_entry": ("fh_waitlist_insert", "fh_waitlist_relay"),
}

_READ = (
    "family_space_id IN (SELECT m.family_space_id FROM space_member m"
    " WHERE m.user_sub = fh_current_user_sub()"
    " AND (fh_current_space_id() IS NULL OR m.family_space_id = fh_current_space_id()))"
)
_WRITE = (
    "family_space_id = fh_current_space_id() AND EXISTS (SELECT 1 FROM space_member m"
    " WHERE m.family_space_id = fh_current_space_id()"
    " AND m.user_sub = fh_current_user_sub() AND m.role <> 'viewer')"
)


def _create_rls_functions() -> None:
    op.execute(
        "CREATE FUNCTION fh_current_user_sub() RETURNS text LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.user_sub', true), '') $$"
    )
    op.execute(
        "CREATE FUNCTION fh_current_space_id() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT NULLIF(current_setting('app.family_space_id', true), '')::uuid $$"
    )


def _force_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _enable_row_level_security() -> None:
    for table in TENANT_TABLES:
        _force_rls(table)
        op.execute(f"CREATE POLICY fh_tenant_select ON {table} FOR SELECT USING ({_READ})")
        op.execute(f"CREATE POLICY fh_tenant_insert ON {table} FOR INSERT WITH CHECK ({_WRITE})")
        if table in APPEND_ONLY_TABLES:
            continue
        op.execute(
            f"CREATE POLICY fh_tenant_update ON {table} FOR UPDATE "
            f"USING ({_WRITE}) WITH CHECK ({_WRITE})"
        )
        op.execute(f"CREATE POLICY fh_tenant_delete ON {table} FOR DELETE USING ({_WRITE})")

    # Membership rows. A policy cannot read its own table (Postgres reports infinite
    # recursion), so writes key on the space setting the application sets only after it has
    # checked that the caller is a steward (or is creating the space).
    _force_rls("space_member")
    op.execute(
        "CREATE POLICY fh_member_select ON space_member FOR SELECT USING ("
        "user_sub = fh_current_user_sub() OR family_space_id = fh_current_space_id())"
    )
    op.execute(
        "CREATE POLICY fh_member_insert ON space_member FOR INSERT WITH CHECK ("
        "family_space_id = fh_current_space_id() AND fh_current_user_sub() IS NOT NULL)"
    )
    op.execute(
        "CREATE POLICY fh_member_update ON space_member FOR UPDATE "
        "USING (family_space_id = fh_current_space_id()) "
        "WITH CHECK (family_space_id = fh_current_space_id())"
    )
    op.execute(
        "CREATE POLICY fh_member_delete ON space_member FOR DELETE "
        "USING (family_space_id = fh_current_space_id())"
    )

    _force_rls("family_space")
    op.execute(
        "CREATE POLICY fh_space_select ON family_space FOR SELECT USING ("
        "id IN (SELECT m.family_space_id FROM space_member m"
        " WHERE m.user_sub = fh_current_user_sub()))"
    )
    op.execute(
        "CREATE POLICY fh_space_insert ON family_space FOR INSERT WITH CHECK ("
        "fh_current_user_sub() IS NOT NULL AND created_by = fh_current_user_sub())"
    )
    steward = (
        "id = fh_current_space_id() AND EXISTS (SELECT 1 FROM space_member m"
        " WHERE m.family_space_id = fh_current_space_id()"
        " AND m.user_sub = fh_current_user_sub() AND m.role = 'steward')"
    )
    op.execute(
        f"CREATE POLICY fh_space_update ON family_space FOR UPDATE "
        f"USING ({steward}) WITH CHECK ({steward})"
    )

    _force_rls("waitlist_entry")
    op.execute("CREATE POLICY fh_waitlist_insert ON waitlist_entry FOR INSERT WITH CHECK (true)")
    relay = "current_setting('app.waitlist_relay', true) = 'on'"
    op.execute(
        f"CREATE POLICY fh_waitlist_relay ON waitlist_entry FOR ALL "
        f"USING ({relay}) WITH CHECK ({relay})"
    )


def _add_trigram_indexes() -> None:
    """Trigram indexes for name and place search, when `pg_trgm` can be installed.

    Search works without them (sequential `LIKE` over the space's rows); they only make it
    faster. The extension is attempted inside a savepoint so a role without the privilege
    does not abort the migration.
    """
    bind = op.get_bind()
    available = bind.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_trgm'")
    ).scalar()
    if not available:
        return
    savepoint = bind.begin_nested()
    try:
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    except sa.exc.DBAPIError:
        savepoint.rollback()
        return
    savepoint.commit()
    op.execute("CREATE INDEX ix_person_search_trgm ON person USING gin (search_text gin_trgm_ops)")
    op.execute("CREATE INDEX ix_place_search_trgm ON place USING gin (search_text gin_trgm_ops)")
