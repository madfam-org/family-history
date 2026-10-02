"""Mutable generator state: id counters, people under construction, places, sources."""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field

from ..compadrazgo import Occasion
from ..data import names as name_data
from ..data import places as place_data
from ..dates import CalendarDate, DateKind, DateValue
from ..dates._calendars import GREGORIAN_MONTHS
from ..events import AssociationRole, EventType
from ..kinship import ParentLink, PartnerLink, PartnerStatus, Sex
from ..names import HYPOCORISTICS, NameForm, NameType, nickname_display, strip_accents
from ._model import SynthAssociation, SynthCitation, SynthEvent, SynthPlace, SynthSource

__all__ = ["Draft", "State", "Union"]


@dataclass(slots=True)
class Draft:
    """A person under construction."""

    id: str
    sex: Sex
    given: str
    paterno: tuple[str | None, str]
    materno: tuple[str | None, str] | None
    birth: dt.date
    generation: int
    minimal: bool = False
    death: dt.date | None = None
    apodo: str | None = None
    extra_names: list[NameForm] = field(default_factory=list)

    def alive_on(self, day: dt.date) -> bool:
        return self.birth <= day and (self.death is None or day < self.death)

    def name_forms(self) -> tuple[NameForm, ...]:
        particle_m, materno = self.materno if self.materno else (None, None)
        usado = None
        words = self.given.split()
        if len(words) > 1 and words[-1][0].isupper():
            usado = words[-1]
        birth = NameForm(
            given_names=(self.given,),
            apellido_paterno=self.paterno[1],
            particle_paterno=self.paterno[0],
            apellido_materno=materno,
            particle_materno=particle_m,
            nombre_usado=usado,
            apodos=(self.apodo,) if self.apodo else (),
            name_type=NameType.BIRTH,
        )
        return (birth, *self.extra_names)


@dataclass(slots=True)
class Union:
    """A couple and how they united."""

    a: Draft
    b: Draft
    status: PartnerStatus
    civil: dt.date | None
    religious: dt.date | None
    divorce: dt.date | None = None

    @property
    def start(self) -> dt.date | None:
        dates = [d for d in (self.civil, self.religious) if d is not None]
        return min(dates) if dates else None


class State:
    """Everything the generator accumulates. All randomness goes through `self.rng`."""

    def __init__(self, seed: int, today: dt.date) -> None:
        # Deterministic fixtures, not security: a seeded PRNG is exactly what is wanted.
        self.rng = random.Random(seed)  # noqa: S311
        self.today = today
        self.people: list[Draft] = []
        self.parent_links: list[ParentLink] = []
        self.unions: list[Union] = []
        self.events: list[SynthEvent] = []
        self.associations: list[SynthAssociation] = []
        self.places: list[SynthPlace] = []
        self.sources: list[SynthSource] = []
        self.citations: list[SynthCitation] = []
        self._counters: dict[str, int] = {}
        self._place_ids: dict[tuple[str, str | None], str] = {}
        self._source_ids: dict[str, str] = {}
        self.parents_of: dict[str, list[str]] = {}
        self.children_of: dict[str, list[str]] = {}
        state = self.rng.choice(place_data.ORIGIN_STATES)
        localities = place_data.FICTIONAL_LOCALITIES
        self.state_name = state
        self.home = self.rng.choice([n for k, n in localities if k in ("rancho", "hacienda")])
        self.alt_home = self.rng.choice([n for k, n in localities if n != self.home])
        self.pueblo = self.rng.choice([n for k, n in localities if k == "pueblo"])
        self.villa = self.rng.choice([n for k, n in localities if k == "villa"])
        self.us_state = self.rng.choice(place_data.US_STATES)
        self.us_town = self.rng.choice(place_data.FICTIONAL_US_LOCALITIES)

    # ids ---------------------------------------------------------------------------------

    def new_id(self, prefix: str) -> str:
        count = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = count
        return f"{prefix}{count:04d}"

    # people ------------------------------------------------------------------------------

    def given_name(self, sex: Sex, year: int) -> str:
        male = sex is Sex.MALE
        if year < 1945:
            pool = name_data.MALE_CLASSIC if male else name_data.FEMALE_CLASSIC
            compound = 0.15
        elif year < 1995:
            classic = name_data.MALE_CLASSIC if male else name_data.FEMALE_CLASSIC
            current = name_data.MALE_CONTEMPORARY if male else name_data.FEMALE_CONTEMPORARY
            pool = classic if self.rng.random() < 0.25 else current
            compound = 0.15
        else:
            pool = name_data.MALE_MODERN if male else name_data.FEMALE_MODERN
            compound = 0.05
        if self.rng.random() < compound:
            pool = name_data.MALE_COMPOUND if male else name_data.FEMALE_COMPOUND
        return self.rng.choice(pool)

    def surname(self) -> tuple[str | None, str]:
        if self.rng.random() < 0.12:
            particle, surname = self.rng.choice(name_data.PARTICLE_SURNAMES)
            return particle, surname
        return None, self.rng.choice(name_data.SURNAMES)

    def add_person(
        self,
        sex: Sex,
        birth: dt.date,
        generation: int,
        paterno: tuple[str | None, str] | None = None,
        materno: tuple[str | None, str] | None = None,
        minimal: bool = False,
    ) -> Draft:
        given = self.given_name(sex, birth.year)
        person = Draft(
            id=self.new_id("I"),
            sex=sex,
            given=given,
            paterno=paterno or self.surname(),
            materno=materno if paterno else self.surname(),
            birth=birth,
            generation=generation,
            minimal=minimal,
        )
        shorts = HYPOCORISTICS.get(strip_accents(given))
        if shorts and self.rng.random() < 0.35:
            person.apodo = nickname_display(self.rng.choice(shorts))
        self.people.append(person)
        return person

    def link_child(self, parent: Draft, child: Draft) -> None:
        self.parent_links.append(ParentLink(parent.id, child.id))
        self.parents_of.setdefault(child.id, []).append(parent.id)
        self.children_of.setdefault(parent.id, []).append(child.id)

    def partner_links(self) -> list[PartnerLink]:
        return [PartnerLink(u.a.id, u.b.id, u.status) for u in self.unions]

    # dates -------------------------------------------------------------------------------

    def day_in(self, year: int) -> dt.date:
        start = dt.date(year, 1, 1)
        day = start + dt.timedelta(days=self.rng.randrange(365))
        return min(day, self.today - dt.timedelta(days=1))

    def after(self, day: dt.date, min_days: int, max_days: int) -> dt.date:
        return day + dt.timedelta(days=self.rng.randint(min_days, max_days))

    @staticmethod
    def exact(day: dt.date) -> DateValue:
        return DateValue(
            DateKind.DATE, CalendarDate(day.year, GREGORIAN_MONTHS[day.month - 1], day.day)
        )

    @staticmethod
    def dated(kind: DateKind, year: int, second: int | None = None) -> DateValue:
        if second is not None:
            return DateValue(kind, CalendarDate(year), CalendarDate(second))
        return DateValue(kind, CalendarDate(year))

    # places, sources, citations ----------------------------------------------------------

    def place(self, name: str, kind: str, parent: str | None, country: str = "MX") -> str:
        key = (name, parent)
        if key not in self._place_ids:
            place_id = self.new_id("L")
            fictional = kind not in ("country", "state")
            self.places.append(SynthPlace(place_id, name, kind, parent, country, fictional))
            self._place_ids[key] = place_id
        return self._place_ids[key]

    def mx_place(self, name: str, kind: str, state: str | None = None) -> str:
        country = self.place(place_data.COUNTRIES["MX"], "country", None)
        state_id = self.place(state or self.state_name, "state", country)
        return self.place(name, kind, state_id)

    def us_place(self, name: str | None = None, kind: str = "locality") -> str:
        country = self.place(place_data.COUNTRIES["US"], "country", None, "US")
        state_id = self.place(self.us_state, "state", country, "US")
        return self.place(name or self.us_town, kind, state_id, "US")

    def parish(self) -> str:
        town = self.mx_place(self.pueblo, "pueblo")
        return self.place(f"Parroquia de {self.pueblo}", "parish", town)

    def cemetery(self) -> str:
        town = self.mx_place(self.pueblo, "pueblo")
        return self.place(f"Panteón de {self.pueblo}", "cemetery", town)

    def source(self, kind: str) -> str:
        if kind not in self._source_ids:
            title, repository = _source_text(kind, self.pueblo, self.villa)
            source_id = self.new_id("S")
            self.sources.append(SynthSource(source_id, title, kind, repository))
            self._source_ids[kind] = source_id
        return self._source_ids[kind]

    def cite(self, kind: str) -> str:
        rng = self.rng
        if kind.startswith("parroquial"):
            page = (
                f"Libro {rng.randint(1, 40)}, foja {rng.randint(1, 300)}, "
                f"partida {rng.randint(1, 900)}"
            )
        elif kind.startswith("civil"):
            page = (
                f"Acta {rng.randint(1, 999)}, foja {rng.randint(1, 250)}, "
                f"libro {rng.randint(1, 30)}"
            )
        elif kind == "oral":
            page = f"Entrevista grabada, minuto {rng.randint(1, 90)}"
        else:
            page = f"Expediente {rng.randint(10000, 99999)}"
        citation_id = self.new_id("C")
        self.citations.append(SynthCitation(citation_id, self.source(kind), page))
        return citation_id

    def add_event(
        self,
        event_type: EventType,
        principals: tuple[str, ...],
        date: DateValue,
        place_id: str | None,
        citation_kind: str | None = None,
        value: str | None = None,
        cause: str | None = None,
    ) -> str:
        citations = (self.cite(citation_kind),) if citation_kind else ()
        event_id = self.new_id("E")
        self.events.append(
            SynthEvent(event_id, event_type, principals, date, place_id, citations, value, cause)
        )
        return event_id

    def associate(
        self,
        event_id: str,
        person: Draft,
        role: AssociationRole,
        occasion: Occasion | None = None,
    ) -> None:
        self.associations.append(
            SynthAssociation(self.new_id("A"), event_id, person.id, role, occasion)
        )


def _source_text(kind: str, pueblo: str, villa: str) -> tuple[str, str]:
    parish_archive = f"Archivo de la Parroquia de {pueblo} (sintético)"
    registry = f"Oficialía del Registro Civil de {villa} (sintético)"
    parish = f"de la Parroquia de {pueblo}"
    texts = {
        "parroquial_bautismos": (f"Libros de bautismos {parish}", parish_archive),
        "parroquial_matrimonios": (
            f"Libros de matrimonios de la Parroquia de {pueblo}",
            parish_archive,
        ),
        "parroquial_entierros": (f"Libros de entierros {parish}", parish_archive),
        "parroquial_confirmaciones": (
            f"Libros de confirmaciones de la Parroquia de {pueblo}",
            parish_archive,
        ),
        "civil_nacimientos": (f"Actas de nacimiento del Registro Civil de {villa}", registry),
        "civil_matrimonios": (f"Actas de matrimonio del Registro Civil de {villa}", registry),
        "civil_defunciones": (f"Actas de defunción del Registro Civil de {villa}", registry),
        "civil_divorcios": (f"Actas de divorcio del Registro Civil de {villa}", registry),
        "bracero": ("Contratos del Programa Bracero", "Archivo de ejemplo (sintético)"),
        "naturalizacion": ("Expedientes de naturalización", "Archivo de ejemplo (sintético)"),
        "oral": ("Entrevistas de historia oral de la familia", "Colección familiar (sintética)"),
    }
    return texts[kind]
