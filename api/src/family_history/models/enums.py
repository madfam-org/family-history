"""Closed vocabularies shared by the models, check constraints and API schemas."""

from __future__ import annotations

from enum import StrEnum


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


class LivingStatus(StrEnum):
    LIVING = "living"
    DECEASED = "deceased"
    UNKNOWN = "unknown"


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


class ParentChildQualifier(StrEnum):
    BIRTH = "birth"
    ADOPTED = "adopted"
    FOSTER = "foster"
    STEP = "step"
    GUARDIAN = "guardian"
    UNKNOWN = "unknown"


class UnionQualifier(StrEnum):
    CIVIL_MARRIAGE = "civil_marriage"
    RELIGIOUS_MARRIAGE = "religious_marriage"
    FREE_UNION = "free_union"
    COHABITATION = "cohabitation"


class UnionStatus(StrEnum):
    ACTIVE = "active"
    DIVORCED = "divorced"
    SEPARATED = "separated"
    WIDOWED = "widowed"
    ANNULLED = "annulled"


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
    GODPARENT = "godparent"
    WITNESS = "witness"


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


class RevisionAction(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


def sql_in(column: str, values: type[StrEnum]) -> str:
    """Check-constraint text: `column IN ('a', 'b')`. Values are code constants, not input."""
    quoted = ", ".join(f"'{member.value}'" for member in values)
    return f"{column} IN ({quoted})"
