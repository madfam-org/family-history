"""Request validation rules that do not need a database."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from family_history.routers.schemas.events import EventCreate, PlaceCreate, RelationshipCreate
from family_history.routers.schemas.evidence import AssertionCreate, CitationCreate
from family_history.routers.schemas.people import NameFormIn, PersonCreate
from family_history.routers.schemas.waitlist import WaitlistRequest

A, B = uuid.uuid4(), uuid.uuid4()


def test_name_form_needs_a_part() -> None:
    with pytest.raises(ValidationError):
        NameFormIn()
    assert NameFormIn(apellido_paterno="  Ramírez ").apellido_paterno == "Ramírez"


def test_person_needs_a_name_and_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PersonCreate(names=[])
    with pytest.raises(ValidationError):
        PersonCreate.model_validate({"names": [{"given": "Ana"}], "curp": "X"})


def test_relationship_qualifiers_follow_type() -> None:
    union = RelationshipCreate(
        type="union", from_person_id=A, to_person_id=B, qualifier="free_union"
    )
    assert union.status is not None and union.status.value == "active"
    RelationshipCreate(type="parent_child", from_person_id=A, to_person_id=B, qualifier="adopted")
    for bad in (
        {"type": "parent_child", "qualifier": "civil_marriage"},
        {"type": "union", "qualifier": "adopted"},
        {"type": "parent_child", "qualifier": "birth", "status": "divorced"},
    ):
        with pytest.raises(ValidationError):
            RelationshipCreate.model_validate({"from_person_id": A, "to_person_id": B, **bad})
    with pytest.raises(ValidationError):
        RelationshipCreate(type="union", from_person_id=A, to_person_id=A, qualifier="free_union")


@pytest.mark.parametrize("value", ["ABT 1890", "BET 1850 AND 1860", "12 MAR 1901", "JULIAN 1700"])
def test_date_values_accept_gedcom_shapes(value: str) -> None:
    event = EventCreate(
        type="birth", date_value=value, participants=[{"person_id": A, "role": "principal"}]
    )
    assert event.date_value == value


@pytest.mark.parametrize("value", ["hacia 1890", "1890-01-01", "ABT  1890", "<script>"])
def test_date_values_reject_free_text(value: str) -> None:
    with pytest.raises(ValidationError):
        EventCreate(
            type="birth", date_value=value, participants=[{"person_id": A, "role": "principal"}]
        )


def test_place_validity_range() -> None:
    with pytest.raises(ValidationError):
        PlaceCreate(
            name="Hacienda", kind="hacienda", valid_from="1900-01-01", valid_to="1800-01-01"
        )


def test_citation_quality_bounds() -> None:
    assert CitationCreate(quality=3).quality == 3
    with pytest.raises(ValidationError):
        CitationCreate(quality=4)


def test_assertion_value_size_is_bounded() -> None:
    with pytest.raises(ValidationError):
        AssertionCreate(subject_type="person", subject_id=A, field="occupation", value="x" * 20_000)


@pytest.mark.parametrize("email", ["sin-arroba", "a@b", "a..b@example.test", "a@-x.test"])
def test_waitlist_rejects_bad_emails(email: str) -> None:
    with pytest.raises(ValidationError):
        WaitlistRequest(email=email, consent=True, aviso_version="2026-10")


def test_waitlist_lowercases_domain_only() -> None:
    request = WaitlistRequest(email="Ana.P@Example.TEST", consent=True, aviso_version="2026-10")
    assert request.email == "Ana.P@example.test"
    assert request.locale == "es-MX"
