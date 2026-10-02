"""Tests for events, living-status inference and sensitivity classes."""

from __future__ import annotations

import datetime as dt

import pytest
from hypothesis import given
from hypothesis import strategies as st

from family_history.domain.dates import parse_date_value
from family_history.domain.dates._calendars import GREGORIAN_MONTHS
from family_history.domain.events import (
    AssociationRole,
    EventType,
    event_spec,
    event_type_from_gedcom,
    role_from_gedcom,
)
from family_history.domain.living import (
    LivingBasis,
    LivingStatus,
    VitalEvent,
    assess_living,
    infer_living_status,
    is_private_by_default,
)
from family_history.domain.sensitivity import (
    FactKind,
    Sensitivity,
    default_sensitivity,
    requires_consent_to_share,
)

TODAY = dt.date(2026, 10, 1)


def _birth(text: str, event_type: EventType = EventType.BIRTH) -> VitalEvent:
    return VitalEvent(event_type, parse_date_value(text))


# --- events -----------------------------------------------------------------------------


def test_every_event_type_has_tag_and_labels() -> None:
    for event_type in EventType:
        spec = event_spec(event_type)
        assert spec is event_type.spec
        assert event_type.gedcom_tag.isupper()
        assert event_type.label_es and event_type.label_en


@pytest.mark.parametrize(
    ("event_type", "tag", "type_text"),
    [
        (EventType.BIRTH, "BIRT", None),
        (EventType.BAPTISM, "BAPM", None),
        (EventType.CHRISTENING, "CHR", None),
        (EventType.CONFIRMATION, "CONF", None),
        (EventType.FIRST_COMMUNION, "FCOM", None),
        (EventType.MARRIAGE, "MARR", None),
        (EventType.CIVIL_MARRIAGE, "MARR", "Matrimonio civil"),
        (EventType.RELIGIOUS_MARRIAGE, "MARR", "Matrimonio religioso"),
        (EventType.DIVORCE, "DIV", None),
        (EventType.DEATH, "DEAT", None),
        (EventType.BURIAL, "BURI", None),
        (EventType.EMIGRATION, "EMIG", None),
        (EventType.IMMIGRATION, "IMMI", None),
        (EventType.NATURALIZATION, "NATU", None),
        (EventType.RESIDENCE, "RESI", None),
        (EventType.OCCUPATION, "OCCU", None),
        (EventType.EDUCATION, "EDUC", None),
        (EventType.QUINCEANERA, "EVEN", "XV años"),
        (EventType.BRACERO_CONTRACT, "EVEN", "Contrato bracero"),
        (EventType.BORDER_CROSSING, "EVEN", "Cruce fronterizo"),
    ],
)
def test_gedcom_mapping_round_trips(event_type: EventType, tag: str, type_text: str | None) -> None:
    assert event_type.gedcom_tag == tag
    assert event_type.gedcom_type == type_text
    assert event_type_from_gedcom(tag, type_text) is event_type


def test_civil_and_religious_marriage_are_distinct() -> None:
    assert len({EventType.CIVIL_MARRIAGE, EventType.RELIGIOUS_MARRIAGE}) == 2
    assert EventType.RELIGIOUS_MARRIAGE.is_sacramental
    assert not EventType.CIVIL_MARRIAGE.is_sacramental
    assert EventType.CIVIL_MARRIAGE.is_family_event


def test_import_aliases_and_fallbacks() -> None:
    assert event_type_from_gedcom("marr", "RELIGIOSO") is EventType.RELIGIOUS_MARRIAGE
    assert event_type_from_gedcom("MARR", "civil") is EventType.CIVIL_MARRIAGE
    assert event_type_from_gedcom("MARR", "por poder") is EventType.MARRIAGE
    assert event_type_from_gedcom("EVEN", "XV AÑOS") is EventType.QUINCEANERA
    assert event_type_from_gedcom("EVEN", "Peregrinación") is EventType.OTHER
    assert event_type_from_gedcom("EVEN") is EventType.OTHER
    assert event_type_from_gedcom("CREM") is EventType.CREMATION
    with pytest.raises(ValueError, match="not a known"):
        event_type_from_gedcom("NAME")


def test_association_roles() -> None:
    assert AssociationRole.GODPARENT.gedcom_role() == ("GODP", None)
    assert AssociationRole.WITNESS.gedcom_role() == ("WITN", None)
    assert AssociationRole.OFFICIANT.gedcom_role() == ("OFFICIATOR", None)
    assert AssociationRole.OTHER.gedcom_role("Chambelán") == ("OTHER", "Chambelán")
    assert AssociationRole.WITNESS.gedcom_role(" de la novia ") == ("WITN", "de la novia")
    with pytest.raises(ValueError, match="PHRASE"):
        AssociationRole.OTHER.gedcom_role()
    assert role_from_gedcom("godp") is AssociationRole.GODPARENT
    assert role_from_gedcom("NGHBR") is AssociationRole.OTHER
    for role in AssociationRole:
        assert role.label_es and role.label_en


# --- living -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("events", "status", "basis"),
    [
        ([], LivingStatus.UNKNOWN, LivingBasis.NO_BIRTH_BOUND),
        ([_birth("1990")], LivingStatus.LIVING, LivingBasis.BORN_WITHIN_WINDOW),
        ([_birth("1 OCT 1916")], LivingStatus.LIVING, LivingBasis.BORN_WITHIN_WINDOW),
        ([_birth("30 SEP 1916")], LivingStatus.PRESUMED_DECEASED, LivingBasis.BORN_BEFORE_WINDOW),
        ([_birth("1850")], LivingStatus.PRESUMED_DECEASED, LivingBasis.BORN_BEFORE_WINDOW),
        # ABT widens by 5 years, which keeps a borderline birth private.
        ([_birth("ABT 1913")], LivingStatus.LIVING, LivingBasis.BORN_WITHIN_WINDOW),
        ([_birth("BEF 1900")], LivingStatus.PRESUMED_DECEASED, LivingBasis.BORN_BEFORE_WINDOW),
        ([_birth("AFT 1950")], LivingStatus.LIVING, LivingBasis.BORN_WITHIN_WINDOW),
        ([_birth("AFT 1850")], LivingStatus.UNKNOWN, LivingBasis.NO_BIRTH_BOUND),
        ([_birth("")], LivingStatus.UNKNOWN, LivingBasis.NO_BIRTH_BOUND),
        ([VitalEvent(EventType.BIRTH)], LivingStatus.UNKNOWN, LivingBasis.NO_BIRTH_BOUND),
        ([_birth("HEBREW 5700")], LivingStatus.UNKNOWN, LivingBasis.NO_BIRTH_BOUND),
        ([_birth("44 BCE")], LivingStatus.PRESUMED_DECEASED, LivingBasis.BORN_BEFORE_WINDOW),
        (
            [_birth("1890", EventType.BAPTISM)],
            LivingStatus.PRESUMED_DECEASED,
            LivingBasis.BORN_BEFORE_WINDOW,
        ),
        # The tightest latest-birth bound wins: baptised 1890 means born by 1890.
        (
            [_birth("AFT 1850"), _birth("1890", EventType.CHRISTENING)],
            LivingStatus.PRESUMED_DECEASED,
            LivingBasis.BORN_BEFORE_WINDOW,
        ),
        (
            [_birth("1990"), VitalEvent(EventType.DEATH, has_evidence=True)],
            LivingStatus.DECEASED,
            LivingBasis.DEATH_EVIDENCE,
        ),
        (
            [VitalEvent(EventType.BURIAL, parse_date_value("2001"), has_evidence=True)],
            LivingStatus.DECEASED,
            LivingBasis.DEATH_EVIDENCE,
        ),
        (
            [VitalEvent(EventType.CREMATION, has_evidence=True)],
            LivingStatus.DECEASED,
            LivingBasis.DEATH_EVIDENCE,
        ),
        # A death without evidence does not make anyone deceased.
        (
            [_birth("1990"), VitalEvent(EventType.DEATH, parse_date_value("2020"))],
            LivingStatus.LIVING,
            LivingBasis.BORN_WITHIN_WINDOW,
        ),
        (
            [VitalEvent(EventType.DEATH, parse_date_value("2020"))],
            LivingStatus.UNKNOWN,
            LivingBasis.NO_BIRTH_BOUND,
        ),
        # Non-vital events never bound birth.
        (
            [VitalEvent(EventType.RESIDENCE, parse_date_value("1850"))],
            LivingStatus.UNKNOWN,
            LivingBasis.NO_BIRTH_BOUND,
        ),
    ],
)
def test_living_rule(events: list[VitalEvent], status: LivingStatus, basis: LivingBasis) -> None:
    assessment = assess_living(events, today=TODAY)
    assert assessment.status is status
    assert assessment.basis is basis
    assert infer_living_status(events, today=TODAY) is status


def test_window_and_margin_are_configurable() -> None:
    events = [_birth("1950")]
    assert infer_living_status(events, today=TODAY, window_years=70) is (
        LivingStatus.PRESUMED_DECEASED
    )
    assert infer_living_status([_birth("ABT 1913")], today=TODAY, approx_years=0) is (
        LivingStatus.PRESUMED_DECEASED
    )
    with pytest.raises(ValueError, match="window_years"):
        assess_living([], today=TODAY, window_years=0)


def test_leap_day_today() -> None:
    assert infer_living_status([_birth("28 FEB 1914")], today=dt.date(2024, 2, 29)) is (
        LivingStatus.LIVING
    )


def test_latest_birth_is_reported() -> None:
    assert assess_living([_birth("MAR 1923")], today=TODAY).latest_birth == dt.date(1923, 3, 31)
    assert assess_living([_birth("44 BCE")], today=TODAY).latest_birth is None


def test_private_by_default() -> None:
    assert is_private_by_default(LivingStatus.LIVING)
    assert is_private_by_default(LivingStatus.UNKNOWN)
    assert not is_private_by_default(LivingStatus.DECEASED)
    assert not is_private_by_default(LivingStatus.PRESUMED_DECEASED)
    assert assess_living([], today=TODAY).private_by_default


def test_contract_values_and_labels() -> None:
    assert {s.contract_value for s in LivingStatus} == {"living", "deceased", "unknown"}
    assert LivingStatus.PRESUMED_DECEASED.contract_value == "deceased"
    for status in LivingStatus:
        assert status.label_es and status.label_en


@given(st.dates(min_value=dt.date(1, 1, 1), max_value=dt.date(2100, 12, 31)))
def test_exact_birth_dates_split_cleanly_at_the_window(birth: dt.date) -> None:
    month = GREGORIAN_MONTHS[birth.month - 1]
    status = infer_living_status([_birth(f"{birth.day} {month} {birth.year}")], today=TODAY)
    expected = (
        LivingStatus.LIVING if birth >= dt.date(1916, 10, 1) else LivingStatus.PRESUMED_DECEASED
    )
    assert status is expected


@given(st.booleans(), st.integers(1800, 2026))
def test_evidenced_death_always_wins(has_birth: bool, year: int) -> None:
    events = [VitalEvent(EventType.DEATH, has_evidence=True)]
    if has_birth:
        events.append(_birth(str(year)))
    assert infer_living_status(events, today=TODAY) is LivingStatus.DECEASED


# --- sensitivity ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (EventType.BAPTISM, Sensitivity.RELIGION),
        (EventType.CHRISTENING, Sensitivity.RELIGION),
        (EventType.CONFIRMATION, Sensitivity.RELIGION),
        (EventType.FIRST_COMMUNION, Sensitivity.RELIGION),
        (EventType.RELIGIOUS_MARRIAGE, Sensitivity.RELIGION),
        (EventType.CIVIL_MARRIAGE, Sensitivity.NONE),
        (EventType.BIRTH, Sensitivity.NONE),
        (EventType.BORDER_CROSSING, Sensitivity.NONE),
        (FactKind.CAUSE_OF_DEATH, Sensitivity.HEALTH),
        (FactKind.MEDICAL_NOTE, Sensitivity.HEALTH),
        (FactKind.RELIGIOUS_AFFILIATION, Sensitivity.RELIGION),
        (FactKind.ETHNIC_ORIGIN, Sensitivity.ETHNICITY),
        (FactKind.POLITICAL_AFFILIATION, Sensitivity.POLITICAL),
    ],
)
def test_default_sensitivity(kind: EventType | FactKind, expected: Sensitivity) -> None:
    assert default_sensitivity(kind) is expected


def test_consent_matrix() -> None:
    for sensitivity in Sensitivity:
        for status in LivingStatus:
            needs = requires_consent_to_share(status, sensitivity)
            expected = sensitivity is not Sensitivity.NONE and status in (
                LivingStatus.LIVING,
                LivingStatus.UNKNOWN,
            )
            assert needs is expected
    assert requires_consent_to_share(LivingStatus.LIVING, Sensitivity.HEALTH)
    assert not requires_consent_to_share(LivingStatus.DECEASED, Sensitivity.RELIGION)


def test_sensitivity_labels() -> None:
    assert Sensitivity.HEALTH.label_es == "Salud"
    assert not Sensitivity.NONE.is_sensitive
    for sensitivity in Sensitivity:
        assert sensitivity.label_es and sensitivity.label_en
