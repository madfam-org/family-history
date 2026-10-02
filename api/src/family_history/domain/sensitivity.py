"""Sensitivity classes for facts, after Mexico's LFPDPPP (DOF 2025-03-20).

The law treats data that reveal religion, health, genetic make-up, ethnic origin, sexual life
and political opinion as sensitive (Art. 2, fraction VI) and requires express consent to
process it (Art. 8). docs/PRIVACY.md turns that into product rules: sacramental events default
to `RELIGION`, causes of death and medical notes to `HEALTH`, and a sensitive fact about a
living (or possibly living) person stays with its contributor until that person consents.
"""

from __future__ import annotations

from enum import StrEnum

from .events import EventType
from .living import LivingStatus

__all__ = [
    "FactKind",
    "Sensitivity",
    "default_sensitivity",
    "requires_consent_to_share",
]


class Sensitivity(StrEnum):
    """The privacy class of a fact."""

    NONE = "none"
    RELIGION = "religion"
    HEALTH = "health"
    GENETIC = "genetic"
    ETHNICITY = "ethnicity"
    SEXUAL = "sexual"
    POLITICAL = "political"

    @property
    def is_sensitive(self) -> bool:
        return self is not Sensitivity.NONE

    @property
    def label_es(self) -> str:
        return _LABELS[self][0]

    @property
    def label_en(self) -> str:
        return _LABELS[self][1]


_LABELS: dict[Sensitivity, tuple[str, str]] = {
    Sensitivity.NONE: ("No sensible", "Not sensitive"),
    Sensitivity.RELIGION: ("Creencias religiosas", "Religious beliefs"),
    Sensitivity.HEALTH: ("Salud", "Health"),
    Sensitivity.GENETIC: ("Información genética", "Genetic information"),
    Sensitivity.ETHNICITY: ("Origen étnico", "Ethnic origin"),
    Sensitivity.SEXUAL: ("Vida sexual", "Sexual life"),
    Sensitivity.POLITICAL: ("Opiniones políticas", "Political opinions"),
}


class FactKind(StrEnum):
    """Facts that are not events but carry a default sensitivity."""

    CAUSE_OF_DEATH = "cause_of_death"
    MEDICAL_NOTE = "medical_note"
    RELIGIOUS_AFFILIATION = "religious_affiliation"
    ETHNIC_ORIGIN = "ethnic_origin"
    POLITICAL_AFFILIATION = "political_affiliation"


_FACT_DEFAULTS: dict[FactKind, Sensitivity] = {
    FactKind.CAUSE_OF_DEATH: Sensitivity.HEALTH,
    FactKind.MEDICAL_NOTE: Sensitivity.HEALTH,
    FactKind.RELIGIOUS_AFFILIATION: Sensitivity.RELIGION,
    FactKind.ETHNIC_ORIGIN: Sensitivity.ETHNICITY,
    FactKind.POLITICAL_AFFILIATION: Sensitivity.POLITICAL,
}


def default_sensitivity(kind: EventType | FactKind) -> Sensitivity:
    """The class a new fact starts with; a steward may raise it, never silently lower it.

    Sacramental events (bautizo, confirmación, primera comunión, matrimonio religioso) are
    `RELIGION`; causes of death and medical notes are `HEALTH`.
    """
    if isinstance(kind, FactKind):
        return _FACT_DEFAULTS[kind]
    return Sensitivity.RELIGION if kind.is_sacramental else Sensitivity.NONE


def requires_consent_to_share(living_status: LivingStatus, sensitivity: Sensitivity) -> bool:
    """True when sharing the fact beyond its contributor needs the person's express consent.

    That is any sensitive fact about someone who is, or may be, alive (`LIVING` or `UNKNOWN`).
    """
    if not sensitivity.is_sensitive:
        return False
    return living_status in (LivingStatus.LIVING, LivingStatus.UNKNOWN)
