"""Deterministic synthetic family generator and its lexicon.

`generate_family(seed)` builds a plausible Mexican family of 3 to 6 generations from the
lexicon in `family_history.domain.data`: dual surnames passed down from both parents,
sacraments with padrinos, civil and religious marriages and unión libre, bracero contracts and
border crossings, deaths with burials for the old generations and living young generations.
The same seed and `today` always give the same family. No real person is represented; every
locality is invented and named so.
"""

from __future__ import annotations

import datetime as dt

from ._life import add_life_events
from ._model import (
    SynthAssociation,
    SynthCitation,
    SyntheticFamily,
    SyntheticLexicon,
    SynthEvent,
    SynthPerson,
    SynthPlace,
    SynthSource,
    synthetic_lexicon,
)
from ._state import State
from ._tree import build_tree, decide_deaths

__all__ = [
    "DEFAULT_TODAY",
    "MAX_GENERATIONS",
    "MIN_GENERATIONS",
    "SynthAssociation",
    "SynthCitation",
    "SynthEvent",
    "SynthPerson",
    "SynthPlace",
    "SynthSource",
    "SyntheticFamily",
    "SyntheticLexicon",
    "generate_family",
    "synthetic_lexicon",
]

MIN_GENERATIONS = 3
MAX_GENERATIONS = 6
#: A fixed reference day so fixtures do not drift with the calendar.
DEFAULT_TODAY = dt.date(2026, 10, 1)


def generate_family(
    seed: int, generations: int = 4, today: dt.date = DEFAULT_TODAY
) -> SyntheticFamily:
    """Generate a synthetic family. Pure: the result depends only on the arguments."""
    if not MIN_GENERATIONS <= generations <= MAX_GENERATIONS:
        raise ValueError(
            f"generations must be between {MIN_GENERATIONS} and {MAX_GENERATIONS}"
        )
    state = State(seed, today)
    build_tree(state, generations)
    decide_deaths(state)
    add_life_events(state)
    people = tuple(
        SynthPerson(p.id, p.sex, p.name_forms(), p.generation) for p in state.people
    )
    return SyntheticFamily(
        seed=seed,
        today=today,
        people=people,
        parent_links=tuple(state.parent_links),
        partner_links=tuple(state.partner_links()),
        events=tuple(state.events),
        associations=tuple(state.associations),
        places=tuple(state.places),
        sources=tuple(state.sources),
        citations=tuple(state.citations),
    )
