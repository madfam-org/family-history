"""Life events: sacraments with padrinos, schooling, work, migration, unions and deaths."""

from __future__ import annotations

import datetime as dt

from ..compadrazgo import Occasion
from ..data import places as place_data
from ..dates import CalendarDate, DateKind, DateValue
from ..dates._calendars import GREGORIAN_MONTHS
from ..events import AssociationRole, EventType
from ..kinship import PartnerStatus, Sex
from ..names import NameForm, NameType
from ._state import Draft, State, Union
from ._tree import decide_deaths

__all__ = ["add_life_events"]

_EDUCATION = ("primaria", "secundaria", "preparatoria", "escuela normal", "licenciatura")


class _Life:
    def __init__(self, state: State) -> None:
        self.s = state
        self.by_id = {person.id: person for person in state.people}
        self.partners: dict[str, list[Draft]] = {}
        for union in state.unions:
            self.partners.setdefault(union.a.id, []).append(union.b)
            self.partners.setdefault(union.b.id, []).append(union.a)
        self.outsider_pairs: dict[tuple[str, ...], list[Draft]] = {}

    # godparents --------------------------------------------------------------------------

    def _relatives_as_godparents(self, child: Draft, day: dt.date) -> list[Draft]:
        s = self.s
        pairs: list[list[Draft]] = []
        for parent_id in s.parents_of.get(child.id, []):
            for grandparent_id in s.parents_of.get(parent_id, []):
                for sibling_id in s.children_of.get(grandparent_id, []):
                    if sibling_id == parent_id:
                        continue
                    sibling = self.by_id[sibling_id]
                    for partner in self.partners.get(sibling_id) or [sibling]:
                        pair = [sibling] if partner is sibling else [sibling, partner]
                        pair.sort(key=lambda person: person.id)
                        if all(_adult_alive(q, day) for q in pair) and pair not in pairs:
                            pairs.append(pair)
        return s.rng.choice(pairs) if pairs and s.rng.random() < 0.7 else []

    def godparents(self, child: Draft, day: dt.date) -> list[Draft]:
        relatives = self._relatives_as_godparents(child, day)
        if relatives:
            return relatives
        key = tuple(sorted(self.s.parents_of.get(child.id, [child.id])))
        cached = self.outsider_pairs.get(key)
        if cached and all(_adult_alive(p, day) for p in cached) and self.s.rng.random() < 0.5:
            return cached
        pair = self._new_outsider_pair(child, day)
        self.outsider_pairs[key] = pair
        return pair

    def _new_outsider_pair(self, child: Draft, day: dt.date) -> list[Draft]:
        s = self.s
        year = max(child.birth.year - s.rng.randint(20, 35), 1)
        made: list[Draft] = []
        for sex in (Sex.MALE, Sex.FEMALE):
            born = s.day_in(year + s.rng.randint(-3, 3))
            person = s.add_person(sex, born, max(child.generation - 1, 0), minimal=True)
            self.by_id[person.id] = person
            made.append(person)
        decide_deaths(s, made)
        for person in made:
            if person.death is not None and person.death <= day:
                person.death = None
        union = Union(made[0], made[1], PartnerStatus.MARRIED, None, None)
        s.unions.append(union)
        self.partners.setdefault(made[0].id, []).append(made[1])
        self.partners.setdefault(made[1].id, []).append(made[0])
        return made

    def _sponsor(self, event_id: str, people: list[Draft], occasion: Occasion) -> None:
        for person in people:
            self.s.associate(event_id, person, AssociationRole.GODPARENT, occasion)

    # per person --------------------------------------------------------------------------

    def person(self, p: Draft) -> None:
        s = self.s
        end = p.death or s.today
        self._birth(p)
        if p.minimal:
            self._death(p)
            return
        self._sacraments(p, end)
        if p.sex is Sex.FEMALE and p.birth.year >= 1950 and s.rng.random() < 0.5:
            day = _years_after(p.birth, 15)
            if day < end:
                event = s.add_event(EventType.QUINCEANERA, (p.id,), s.exact(day),
                                    s.mx_place(s.pueblo, "pueblo"), "oral")  # fmt: skip
                self._sponsor(event, self.godparents(p, day), Occasion.XV_ANOS)
        self._work_and_school(p, end)
        self._migration(p, end)
        self._death(p)

    def _birth(self, p: Draft) -> None:
        s = self.s
        year = p.birth.year
        if p.minimal:
            s.add_event(EventType.BIRTH, (p.id,), s.dated(DateKind.ABOUT, year), None)
            return
        roll = s.rng.random()
        if year < 1880 and roll < 0.4:
            date = s.dated(DateKind.ABOUT, year)
        elif year < 1880 and roll < 0.6:
            date = s.dated(DateKind.DATE, year)
        else:
            date = s.exact(p.birth)
        home = s.home if s.rng.random() < 0.75 else s.alt_home
        kind = "civil_nacimientos" if year >= 1870 and s.rng.random() < 0.8 else None
        s.add_event(EventType.BIRTH, (p.id,), date, s.mx_place(home, "locality"), kind)

    def _sacraments(self, p: Draft, end: dt.date) -> None:
        s = self.s
        if s.rng.random() >= (0.92 if p.birth.year < 2005 else 0.6):
            return
        day = s.after(p.birth, 3, 60)
        if day >= end:
            return
        event = s.add_event(EventType.BAPTISM, (p.id,), s.exact(day), s.parish(),
                            "parroquial_bautismos")  # fmt: skip
        self._sponsor(event, self.godparents(p, day), Occasion.BAUTIZO)
        communion = s.after(_years_after(p.birth, s.rng.randint(7, 10)), 0, 200)
        if s.rng.random() < 0.6 and communion < end:
            event = s.add_event(EventType.FIRST_COMMUNION, (p.id,), s.exact(communion),
                                s.parish())  # fmt: skip
            madrina = [g for g in self.godparents(p, communion) if g.sex is Sex.FEMALE]
            self._sponsor(event, madrina[:1], Occasion.PRIMERA_COMUNION)
        confirmation = s.after(_years_after(p.birth, s.rng.randint(10, 14)), 0, 200)
        if s.rng.random() < 0.4 and confirmation < end:
            event = s.add_event(EventType.CONFIRMATION, (p.id,), s.exact(confirmation),
                                s.parish(), "parroquial_confirmaciones")  # fmt: skip
            sponsor = [g for g in self.godparents(p, confirmation) if g.sex is p.sex]
            self._sponsor(event, sponsor[:1], Occasion.CONFIRMACION)

    def _work_and_school(self, p: Draft, end: dt.date) -> None:
        s = self.s
        if p.birth.year >= 1950 and s.rng.random() < 0.5:
            start = p.birth.year + 6
            finish = start + s.rng.randint(5, 16)
            if finish < end.year:
                s.add_event(EventType.EDUCATION, (p.id,),
                            s.dated(DateKind.FROM_TO, start, finish),
                            s.mx_place(s.villa, "villa"),
                            value=s.rng.choice(_EDUCATION))  # fmt: skip
        start_work = p.birth.year + s.rng.randint(14, 24)
        if start_work < end.year and s.rng.random() < 0.8:
            s.add_event(EventType.OCCUPATION, (p.id,), s.dated(DateKind.FROM, start_work),
                        None, value=s.rng.choice(place_data.OCCUPATIONS))  # fmt: skip

    def _migration(self, p: Draft, end: dt.date) -> None:
        s = self.s
        if p.sex is Sex.MALE and 1915 <= p.birth.year <= 1944 and s.rng.random() < 0.4:
            first = max(1942, p.birth.year + 18)
            last = min(1964, p.birth.year + 40, end.year - 1)
            if first <= last:
                day = s.day_in(s.rng.randint(first, last))
                center = s.mx_place(s.rng.choice(place_data.BRACERO_CENTERS), "office")
                s.add_event(EventType.BRACERO_CONTRACT, (p.id,), s.exact(day), center,
                            "bracero")  # fmt: skip
                crossing = s.after(day, 2, 10)
                if crossing < end:
                    self._cross(p, crossing, end, settle=s.rng.random() < 0.3)
        elif 1955 <= p.birth.year <= 2002 and s.rng.random() < 0.2:
            crossing = _years_after(p.birth, s.rng.randint(17, 28))
            if crossing < end:
                self._cross(p, crossing, end, settle=True)

    def _cross(self, p: Draft, day: dt.date, end: dt.date, settle: bool) -> None:
        s = self.s
        garita = s.mx_place(s.rng.choice(place_data.BORDER_CROSSINGS), "border_crossing",
                            "Chihuahua")  # fmt: skip
        s.add_event(EventType.BORDER_CROSSING, (p.id,), s.exact(day), garita, "oral")
        if not settle:
            return
        s.add_event(EventType.IMMIGRATION, (p.id,), s.exact(s.after(day, 1, 30)), s.us_place())
        s.add_event(EventType.RESIDENCE, (p.id,), s.dated(DateKind.FROM, day.year), s.us_place())
        naturalized = _years_after(day, s.rng.randint(8, 20))
        if naturalized < end and s.rng.random() < 0.35:
            s.add_event(EventType.NATURALIZATION, (p.id,), s.exact(naturalized), s.us_place(),
                        "naturalizacion")  # fmt: skip
        husbands = [q for q in self.partners.get(p.id, []) if q.sex is Sex.MALE]
        if p.sex is Sex.FEMALE and husbands:
            p.extra_names.append(NameForm(given_names=(p.given,),
                                          apellido_paterno=husbands[0].paterno[1],
                                          name_type=NameType.MARRIED, lang="en-US"))  # fmt: skip

    def _death(self, p: Draft) -> None:
        s = self.s
        if p.death is None:
            return
        documented = s.rng.random() < 0.9
        if p.death.year < 1950 and s.rng.random() < 0.08:
            date: DateValue = s.dated(DateKind.BETWEEN, p.death.year - 2, p.death.year)
        elif p.death.year < 1900 and s.rng.random() < 0.2:
            month = GREGORIAN_MONTHS[p.death.month - 1]
            date = DateValue(DateKind.DATE, CalendarDate(p.death.year, month))
        else:
            date = s.exact(p.death)
        kind = "civil_defunciones" if p.death.year >= 1870 else "parroquial_entierros"
        cause = s.rng.choice(place_data.CAUSES_OF_DEATH) if s.rng.random() < 0.5 else None
        s.add_event(EventType.DEATH, (p.id,), date, s.mx_place(s.pueblo, "pueblo"),
                    kind if documented else None, cause=cause)  # fmt: skip
        if documented and s.rng.random() < 0.85:
            burial = min(s.after(p.death, 1, 2), s.today - dt.timedelta(days=1))
            s.add_event(EventType.BURIAL, (p.id,), s.exact(burial), s.cemetery(),
                        "parroquial_entierros")  # fmt: skip

    # unions ------------------------------------------------------------------------------

    def union(self, u: Union) -> None:
        s = self.s
        if u.a.minimal and u.b.minimal:
            return
        couple = (u.a.id, u.b.id)
        if u.civil:
            event = s.add_event(EventType.CIVIL_MARRIAGE, couple, s.exact(u.civil),
                                s.mx_place(s.villa, "villa"), "civil_matrimonios")  # fmt: skip
            for witness in self._witnesses(u, u.civil):
                s.associate(event, witness, AssociationRole.WITNESS)
        if u.religious:
            event = s.add_event(EventType.RELIGIOUS_MARRIAGE, couple, s.exact(u.religious),
                                s.parish(), "parroquial_matrimonios")  # fmt: skip
            padrinos = self.godparents(u.a, u.religious)
            self._sponsor(event, [p for p in padrinos if p.id not in couple], Occasion.BODA)
        if u.divorce:
            s.add_event(EventType.DIVORCE, couple, s.exact(u.divorce),
                        s.mx_place(s.villa, "villa"), "civil_divorcios")  # fmt: skip

    def _witnesses(self, u: Union, day: dt.date) -> list[Draft]:
        s = self.s
        found: list[Draft] = []
        for member in (u.a, u.b):
            for parent_id in s.parents_of.get(member.id, []):
                for sibling_id in s.children_of.get(parent_id, []):
                    sibling = self.by_id[sibling_id]
                    eligible = sibling_id != member.id and _adult_alive(sibling, day)
                    if eligible and sibling not in found:
                        found.append(sibling)
        return found[:2]


def _adult_alive(person: Draft, day: dt.date) -> bool:
    return person.alive_on(day) and _years_after(person.birth, 14) <= day


def _years_after(day: dt.date, years: int) -> dt.date:
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def add_life_events(state: State) -> None:
    """Add every life and union event. People created on the way (godparents) get theirs."""
    life = _Life(state)
    index = 0
    while index < len(state.people):
        life.person(state.people[index])
        index += 1
    for union in list(state.unions):
        life.union(union)
    # Godparents created while adding union events still need their own events.
    while index < len(state.people):
        life.person(state.people[index])
        index += 1
