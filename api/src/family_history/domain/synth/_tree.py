"""Family structure: founders, unions, children and deaths across the generations."""

from __future__ import annotations

import datetime as dt

from ..kinship import PartnerStatus, Sex
from ._state import Draft, State, Union

__all__ = ["build_tree", "decide_deaths"]

_MAX_COUPLES_PER_GENERATION = 3


def _union_kind(state: State, year: int) -> tuple[bool, bool]:
    """Return `(civil, religious)`; neither means unión libre."""
    roll = state.rng.random()
    table: tuple[tuple[float, tuple[bool, bool]], ...]
    if year < 1930:
        table = ((0.40, (False, True)), (0.85, (True, True)), (1.0, (False, False)))
    elif year < 1970:
        table = ((0.70, (True, True)), (0.75, (True, False)), (0.85, (False, True)),
                 (1.0, (False, False)))  # fmt: skip
    else:
        table = ((0.50, (True, True)), (0.70, (True, False)), (1.0, (False, False)))
    for threshold, kind in table:
        if roll < threshold:
            return kind
    return False, False


def _unite(state: State, a: Draft, b: Draft, year: int) -> Union:
    earliest = max(a.birth, b.birth).year + 17
    year = min(max(year, earliest), state.today.year - 1)
    civil, religious = _union_kind(state, year)
    civil_day = state.day_in(year) if civil else None
    religious_day = None
    if religious:
        religious_day = state.after(civil_day, 0, 21) if civil_day else state.day_in(year)
        religious_day = min(religious_day, state.today - dt.timedelta(days=1))
    status = PartnerStatus.MARRIED if civil or religious else PartnerStatus.UNION_LIBRE
    union = Union(a, b, status, civil_day, religious_day)
    if civil_day and year > 1975 and state.rng.random() < 0.12:
        divorce = state.after(civil_day, 5 * 365, 15 * 365)
        if divorce < state.today:
            union.divorce = divorce
            union.status = PartnerStatus.DIVORCED
    state.unions.append(union)
    return union


def _spouse_for(state: State, person: Draft, generation: int) -> Draft:
    sex = Sex.FEMALE if person.sex is Sex.MALE else Sex.MALE
    born = state.day_in(person.birth.year + state.rng.randint(-4, 3))
    return state.add_person(sex, born, generation)


def _children(state: State, union: Union, generation: int, target_year: int) -> list[Draft]:
    father, mother = (union.a, union.b) if union.a.sex is Sex.MALE else (union.b, union.a)
    old = target_year < 1950
    count = state.rng.randint(3, 7) if old else state.rng.randint(1, 4)
    year = max(target_year - state.rng.randint(0, 3), mother.birth.year + 17)
    if union.start is not None:
        year = max(year, union.start.year)
    children: list[Draft] = []
    for _ in range(count):
        if year > min(mother.birth.year + 44, state.today.year):
            break
        birth = state.day_in(year)
        if union.start is not None and birth < union.start:
            birth = state.after(union.start, 280, 400)
        if birth >= state.today:
            break
        sex = Sex.MALE if state.rng.random() < 0.5 else Sex.FEMALE
        child = state.add_person(sex, birth, generation, father.paterno, (mother.paterno))
        state.link_child(father, child)
        state.link_child(mother, child)
        children.append(child)
        year = birth.year + state.rng.randint(1, 3)
    return children


def build_tree(state: State, generations: int) -> None:
    """Create founders and `generations` levels of descendants with their unions."""
    gap = state.rng.randint(25, 29)
    youngest = state.today.year - state.rng.randint(4, 16)
    targets = [youngest - gap * (generations - 1 - g) for g in range(generations)]
    founder_year = targets[0]
    husband = state.add_person(Sex.MALE, state.day_in(founder_year), 0)
    wife = state.add_person(Sex.FEMALE, state.day_in(founder_year + state.rng.randint(-3, 2)), 0)
    couples = [_unite(state, husband, wife, targets[1] - state.rng.randint(1, 2))]
    for generation in range(1, generations):
        next_couples: list[Union] = []
        last = generation == generations - 1
        for union in couples:
            children = _children(state, union, generation, targets[generation])
            adults = [c for c in children if c.birth.year <= state.today.year - 18]
            if last or not adults:
                continue
            continuing = adults[: state.rng.randint(1, 2)]
            for child in adults:
                if child in continuing and len(next_couples) < _MAX_COUPLES_PER_GENERATION:
                    spouse = _spouse_for(state, child, generation)
                    year = targets[generation + 1] - state.rng.randint(1, 2)
                    next_couples.append(_unite(state, child, spouse, year))
                elif state.rng.random() < 0.25:
                    spouse = _spouse_for(state, child, generation)
                    _unite(state, child, spouse, child.birth.year + state.rng.randint(20, 30))
        if not last and not next_couples:
            raise RuntimeError("generator produced no couple to continue the family")
        couples = next_couples


def _death_probability(age: int) -> float:
    if age >= 100:
        return 1.0
    if age >= 85:
        return 0.75
    if age >= 70:
        return 0.4
    if age >= 50:
        return 0.12
    if age >= 20:
        return 0.03
    return 0.0


def decide_deaths(state: State, people: list[Draft] | None = None) -> None:
    """Give some people a death date, never before their last child or union."""
    floors: dict[str, dt.date] = {}
    for union in state.unions:
        for member in (union.a, union.b):
            start = union.start or member.birth
            floors[member.id] = max(floors.get(member.id, member.birth), start)
    by_id = {person.id: person for person in state.people}
    for child_id, parent_ids in state.parents_of.items():
        for parent_id in parent_ids:
            floors[parent_id] = max(floors.get(parent_id, by_id[parent_id].birth),
                                    by_id[child_id].birth)  # fmt: skip
    for person in people if people is not None else state.people:
        age = state.today.year - person.birth.year
        if state.rng.random() >= _death_probability(age):
            continue
        floor = max(floors.get(person.id, person.birth), person.birth.replace(day=1)
                    + dt.timedelta(days=365 * 18))  # fmt: skip
        ceiling = min(person.birth + dt.timedelta(days=365 * 98), state.today - dt.timedelta(1))
        if floor >= ceiling:
            continue
        span = (ceiling - floor).days
        person.death = floor + dt.timedelta(days=state.rng.randint(1, span))
