"""`seed-synth`: persist `domain.synth.generate_family` into an existing family space.

It runs as the space's first steward, under row-level security like any write, and refuses
when `FH_ENV` is `production` (or unset, which means production).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from family_history.auth import Principal
from family_history.config import Environment, get_settings
from family_history.db.engine import create_database, set_scope
from family_history.interchange.persist import persist_tree
from family_history.interchange.synth import synthetic_tree
from family_history.models import SpaceMember
from family_history.models.enums import Role
from family_history.services.access import SpaceContext


class SeedError(RuntimeError):
    pass


def seed_space(space_id: uuid.UUID, *, seed: int, generations: int) -> dict[str, int]:
    settings = get_settings()
    if settings.env is Environment.PRODUCTION:
        raise SeedError("seed-synth refuses to run when FH_ENV is production (or unset)")
    if settings.database_url is None:
        raise SeedError("DATABASE_URL is not set")
    database = create_database(settings.database_url.get_secret_value(), pool_size=1)
    try:
        with database.sessions() as session:
            set_scope(session, user_sub=None, space_id=space_id)
            steward = session.scalar(
                select(SpaceMember.user_sub)
                .where(
                    SpaceMember.family_space_id == space_id,
                    SpaceMember.role == Role.STEWARD.value,
                )
                .order_by(SpaceMember.created_at, SpaceMember.user_sub)
                .limit(1)
            )
            if steward is None:
                raise SeedError(f"family space {space_id} does not exist or has no steward")
            set_scope(session, user_sub=steward, space_id=space_id)
            ctx = SpaceContext(
                db=session, principal=Principal(sub=steward), space_id=space_id, role=Role.STEWARD
            )
            persisted = persist_tree(ctx, synthetic_tree(seed, generations), source="synthetic")
            session.commit()
            return persisted.counts
    finally:
        database.dispose()
