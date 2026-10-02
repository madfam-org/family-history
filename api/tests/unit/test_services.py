"""Pure services: names, privacy rules, cursors and the rate limiter."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from family_history.errors import APIError
from family_history.models import NameForm
from family_history.models.enums import LivingStatus, Sensitivity
from family_history.services import names
from family_history.services.living import is_private, today_mexico_city
from family_history.services.pagination import decode_cursor, encode_cursor
from family_history.services.privacy import (
    default_field_sensitivity,
    default_sensitivity,
    sensitive_visible,
    treated_as_living,
)
from family_history.services.ratelimit import AddressHasher, SlidingWindowLimiter


def _name(**values: object) -> NameForm:
    defaults: dict[str, object] = {
        "extra_surnames": [],
        "particles": {},
        "nicknames": [],
        "surname_order": "paterno_materno",
        "is_primary": False,
    }
    defaults.update(values)
    return NameForm(**defaults)


def test_normalize_strips_accents_and_case() -> None:
    assert names.normalize("  José  MARÍA Núñez-Güemes ") == "jose maria nunez guemes"


def test_display_name_with_particles_and_order() -> None:
    form = _name(
        given="María Guadalupe",
        nombre_usado="Lupita",
        apellido_paterno="Garza",
        apellido_materno="Treviño",
        particles={"paterno": "de la"},
    )
    # FORMAL style of domain.names.display_name: the nombre de pila, then the surnames.
    assert names.display_name(form) == "María Guadalupe de la Garza Treviño"
    assert names.sorting_display(form) == "Garza Treviño, María Guadalupe de la"
    assert names.sort_key(form) == "garza trevino maria guadalupe de la"
    form.surname_order = "materno_paterno"
    assert names.display_name(form) == "María Guadalupe Treviño de la Garza"


def test_unknown_particles_stay_in_front_of_the_surname() -> None:
    form = _name(given="Ana", apellido_paterno="Garza", particles={"paterno": "xx"})
    assert names.display_name(form) == "Ana xx Garza"
    only_usado = _name(nombre_usado="Lupita")
    assert names.display_name(only_usado) == "Lupita"


def test_search_tokens_cover_every_part_once() -> None:
    forms = [
        _name(given="Ana", apellido_paterno="Pérez", nicknames=["Anita"]),
        _name(given="Ana", apellido_paterno="Pérez", apellido_materno="Ruiz", is_primary=True),
    ]
    # normalize_for_search folds spellings that sound alike (z→s): «Pérez» → «peres».
    assert names.search_tokens(forms) == " ana peres anita ruis "
    assert names.search_tokens([]) == ""
    assert names.primary_name(forms) is forms[1]
    assert names.sort_key(forms[1]) == "perez ruiz ana"


def test_like_pattern_escapes_wildcards() -> None:
    assert names.like_pattern("50%_x") == "%50\\%\\_x%"
    assert names.query_tokens("  Hernández   de  ") == ["hernandez", "de"]


def test_today_is_mexico_city() -> None:
    # 03:00 UTC on 2 October is still 1 October in Mexico City (UTC−06:00).
    assert str(today_mexico_city(datetime(2026, 10, 2, 3, 0, tzinfo=UTC))) == "2026-10-01"
    assert str(today_mexico_city(datetime(2026, 10, 2, 7, 0, tzinfo=UTC))) == "2026-10-02"


def test_is_private_follows_living_status_and_visibility() -> None:
    assert is_private("living", "space") and is_private("unknown", "space")
    assert not is_private("deceased", "space") and not is_private("presumed_deceased", "space")
    assert is_private("deceased", "private")
    assert LivingStatus.PRESUMED_DECEASED.value == "presumed_deceased"


def test_living_and_unknown_are_private_by_default() -> None:
    assert treated_as_living("living") and treated_as_living("unknown")
    assert not treated_as_living("deceased") and not treated_as_living("presumed_deceased")


def test_sacraments_default_to_religion_and_medical_facts_to_health() -> None:
    for sacrament in ("baptism", "christening", "confirmation", "first_communion"):
        assert default_sensitivity(sacrament) is Sensitivity.RELIGION
    assert default_sensitivity("religious_marriage") is Sensitivity.RELIGION
    assert default_sensitivity("civil_marriage") is None
    assert default_sensitivity("birth") is None
    assert default_field_sensitivity("cause_of_death") is Sensitivity.HEALTH
    assert default_field_sensitivity("medical_note") is Sensitivity.HEALTH
    assert default_field_sensitivity("ethnic_origin") is Sensitivity.ETHNICITY
    assert default_field_sensitivity("occupation") is None


def test_sensitive_facts_about_the_living_stay_with_the_author() -> None:
    assert sensitive_visible("religion", "author", "author", about_living=True)
    assert not sensitive_visible("religion", "author", "other", about_living=True)
    assert sensitive_visible("religion", "author", "other", about_living=False)
    assert sensitive_visible(None, "author", "other", about_living=True)


def test_cursor_round_trip_and_rejection() -> None:
    row_id = uuid.uuid4()
    assert decode_cursor(encode_cursor("pérez ana", row_id)) == ("pérez ana", row_id)
    for bad in ("", "!!!", encode_cursor("x", row_id)[:-3] + "zzz"):
        with pytest.raises(APIError) as exc:
            decode_cursor(bad)
        assert exc.value.code == "invalid_cursor"


def test_sliding_window_limiter() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(2, 10, max_keys=2, clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a")
    assert not limiter.allow("a")
    now[0] = 11
    assert limiter.allow("a")
    limiter.allow("b")
    limiter.allow("c")  # evicts the least recently used key
    assert len(limiter._hits) == 2


def test_address_hasher_is_salted() -> None:
    first, second = AddressHasher(), AddressHasher()
    assert first("203.0.113.7") == first("203.0.113.7")
    assert first("203.0.113.7") != second("203.0.113.7")
    assert "203.0.113.7" not in first("203.0.113.7")
