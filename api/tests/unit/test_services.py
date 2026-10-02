"""Pure services: names, privacy rules, cursors and the rate limiter."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from family_history.errors import APIError
from family_history.models import NameForm
from family_history.models.enums import LivingStatus, Sensitivity
from family_history.services import names
from family_history.services.pagination import decode_cursor, encode_cursor
from family_history.services.privacy import (
    LifeEvent,
    compute_living_status,
    default_sensitivity,
    sensitive_visible,
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
    assert names.display_name(form) == "Lupita de la Garza Treviño"
    form.surname_order = "materno_paterno"
    assert names.display_name(form) == "Lupita Treviño de la Garza"


def test_search_text_covers_every_part_once() -> None:
    forms = [
        _name(given="Ana", apellido_paterno="Pérez", nicknames=["Anita"]),
        _name(given="Ana", apellido_paterno="Pérez", apellido_materno="Ruiz", is_primary=True),
    ]
    assert names.search_text(forms) == "ana perez anita ruiz"
    assert names.primary_name(forms) is forms[1]
    assert names.sort_name(forms[1]) == "perez ruiz ana"


def test_like_pattern_escapes_wildcards() -> None:
    assert names.like_pattern("50%_x") == "%50\\%\\_x%"
    assert names.search_tokens("  Hernández   de  ") == ["hernandez", "de"]


def test_living_status_rules() -> None:
    today = date(2026, 10, 1)
    assert compute_living_status([], today) is LivingStatus.LIVING
    assert compute_living_status([LifeEvent("death", None)], today) is LivingStatus.DECEASED
    old_birth = LifeEvent("birth", date(1900, 1, 1))
    assert compute_living_status([old_birth], today) is LivingStatus.UNKNOWN
    recent_birth = LifeEvent("birth", date(1950, 1, 1))
    assert compute_living_status([recent_birth], today) is LivingStatus.LIVING


def test_sacraments_default_to_religion_and_medical_to_health() -> None:
    assert default_sensitivity("baptism") is Sensitivity.RELIGION
    assert default_sensitivity("religious_marriage") is Sensitivity.RELIGION
    assert default_sensitivity("medical") is Sensitivity.HEALTH
    assert default_sensitivity("birth") is None


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
