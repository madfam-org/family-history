"""SQLAlchemy models for the M1 core. Importing this package registers every table."""

from family_history.models.audit import Revision, WaitlistEntry
from family_history.models.base import Base
from family_history.models.event import Association, Event, EventParticipant, Place
from family_history.models.evidence import Assertion, Citation, Source
from family_history.models.person import NameForm, Person, Relationship
from family_history.models.space import FamilySpace, SpaceMember

TENANT_TABLES: tuple[str, ...] = (
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

__all__ = [
    "TENANT_TABLES",
    "Assertion",
    "Association",
    "Base",
    "Citation",
    "Event",
    "EventParticipant",
    "FamilySpace",
    "NameForm",
    "Person",
    "Place",
    "Relationship",
    "Revision",
    "Source",
    "SpaceMember",
    "WaitlistEntry",
]
