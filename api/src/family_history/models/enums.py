"""Closed vocabularies shared by the models, check constraints and API schemas."""

from __future__ import annotations

from enum import StrEnum

# The genealogy vocabularies come from the domain library; the API stores their values.
from family_history.domain.events import EventType
from family_history.domain.kinship import PartnerStatus, Pedigree
from family_history.domain.living import LivingStatus

__all__ = [
    "ROLE_RANK",
    "AssertionStatus",
    "AssociationRole",
    "EventType",
    "ExportFormat",
    "JobKind",
    "JobStatus",
    "LivingStatus",
    "NameType",
    "ParticipantRole",
    "PartnerStatus",
    "Pedigree",
    "PlaceKind",
    "RelationshipType",
    "RevisionAction",
    "Role",
    "Sensitivity",
    "Sex",
    "SourceType",
    "SubjectType",
    "SurnameOrder",
    "Visibility",
    "sql_in",
]


class Role(StrEnum):
    STEWARD = "steward"
    EDITOR = "editor"
    CONTRIBUTOR = "contributor"
    VIEWER = "viewer"


ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.CONTRIBUTOR: 1,
    Role.EDITOR: 2,
    Role.STEWARD: 3,
}


class Sex(StrEnum):
    M = "M"
    F = "F"
    X = "X"
    U = "U"


class Visibility(StrEnum):
    SPACE = "space"
    PRIVATE = "private"
    PUBLIC_MEMORIAL = "public_memorial"


class NameType(StrEnum):
    BIRTH = "birth"
    BAPTISMAL = "baptismal"
    MARRIED = "married"
    RELIGIOUS = "religious"
    ALSO_KNOWN_AS = "aka"
    IMMIGRANT = "immigrant"
    OTHER = "other"


class SurnameOrder(StrEnum):
    PATERNO_MATERNO = "paterno_materno"
    MATERNO_PATERNO = "materno_paterno"
    SINGLE = "single"


class RelationshipType(StrEnum):
    PARENT_CHILD = "parent_child"
    UNION = "union"


class ParticipantRole(StrEnum):
    PRINCIPAL = "principal"
    SPOUSE = "spouse"
    PARENT = "parent"
    GODPARENT = "godparent"
    WITNESS = "witness"
    OFFICIANT = "officiant"
    INFORMANT = "informant"
    OTHER = "other"


class AssociationRole(StrEnum):
    """A person's role at someone else's event. Maps to `domain.events.AssociationRole`
    (GEDCOM `ROLE`: GODP, WITN, OFFICIATOR, OTHER with a phrase)."""

    GODPARENT = "godparent"
    WITNESS = "witness"
    OFFICIANT = "officiant"
    OTHER = "other"


class Sensitivity(StrEnum):
    RELIGION = "religion"
    HEALTH = "health"
    GENETIC = "genetic"
    ETHNICITY = "ethnicity"
    SEXUAL = "sexual"
    POLITICAL = "political"


class PlaceKind(StrEnum):
    PAIS = "pais"
    ESTADO = "estado"
    MUNICIPIO = "municipio"
    LOCALIDAD = "localidad"
    PARROQUIA = "parroquia"
    HACIENDA = "hacienda"
    RANCHO = "rancho"
    OTHER = "other"


class SourceType(StrEnum):
    PARISH_BOOK = "parish_book"
    CIVIL_REGISTRY_ACT = "civil_registry_act"
    ORAL_INTERVIEW = "oral_interview"
    CENSUS = "census"
    NOTARIAL_RECORD = "notarial_record"
    FAMILY_DOCUMENT = "family_document"
    PUBLICATION = "publication"
    WEBSITE = "website"
    OTHER = "other"


class AssertionStatus(StrEnum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    RETRACTED = "retracted"


class SubjectType(StrEnum):
    PERSON = "person"
    EVENT = "event"
    RELATIONSHIP = "relationship"
    PLACE = "place"


class JobKind(StrEnum):
    GEDCOM_IMPORT = "gedcom_import"
    EXPORT = "export"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ExportFormat(StrEnum):
    GEDCOM7 = "gedcom7"
    GEDZIP = "gedzip"
    GEDCOM551 = "gedcom551"
    NATIVE_JSON = "native_json"


class RevisionAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


def sql_in(column: str, values: type[StrEnum]) -> str:
    """Check-constraint text: `column IN ('a', 'b')`. Values are code constants, not input."""
    quoted = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({quoted})"
