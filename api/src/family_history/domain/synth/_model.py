"""Plain dataclasses for a generated synthetic family, and the synthetic lexicon."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..compadrazgo import GodparentLink, Occasion
from ..data import names as name_data
from ..data import places as place_data
from ..dates import DateValue
from ..events import AssociationRole, EventType
from ..kinship import FamilyGraph, ParentLink, PartnerLink, Sex
from ..living import LivingStatus, VitalEvent, infer_living_status
from ..names import HYPOCORISTICS, NameForm, nickname_display
from ..sensitivity import Sensitivity, default_sensitivity

__all__ = [
    "SynthAssociation",
    "SynthCitation",
    "SynthEvent",
    "SynthPerson",
    "SynthPlace",
    "SynthSource",
    "SyntheticFamily",
    "SyntheticLexicon",
    "synthetic_lexicon",
]


@dataclass(frozen=True, slots=True)
class SynthPlace:
    """A place. `fictional` is True for every locality; states and countries are real."""

    id: str
    name: str
    kind: str
    parent_id: str | None
    country: str
    fictional: bool


@dataclass(frozen=True, slots=True)
class SynthPerson:
    """A synthetic person. `names[0]` is the birth name; later forms are stated by records."""

    id: str
    sex: Sex
    names: tuple[NameForm, ...]
    generation: int


@dataclass(frozen=True, slots=True)
class SynthEvent:
    """An event of one person (or of a couple for marriages and divorce).

    `value` holds the GEDCOM payload where the event has one (an occupation); `cause` is a
    cause of death, whose sensitivity is health.
    """

    id: str
    event_type: EventType
    principals: tuple[str, ...]
    date: DateValue
    place_id: str | None
    citation_ids: tuple[str, ...] = ()
    value: str | None = None
    cause: str | None = None

    @property
    def sensitivity(self) -> Sensitivity:
        return default_sensitivity(self.event_type)


@dataclass(frozen=True, slots=True)
class SynthAssociation:
    """`person_id` took part in `event_id` as `role` (godparents carry their occasion)."""

    id: str
    event_id: str
    person_id: str
    role: AssociationRole
    occasion: Occasion | None = None


@dataclass(frozen=True, slots=True)
class SynthSource:
    """A synthetic source: a parish book series, a civil registry series, an interview."""

    id: str
    title: str
    kind: str
    repository: str


@dataclass(frozen=True, slots=True)
class SynthCitation:
    """Where in `source_id` the fact is, e.g. «Libro 12, foja 34, partida 210»."""

    id: str
    source_id: str
    page: str


@dataclass(frozen=True, slots=True)
class SyntheticFamily:
    """Everything one `generate_family` call produced. Plain data; the API lane persists it."""

    seed: int
    today: dt.date
    people: tuple[SynthPerson, ...]
    parent_links: tuple[ParentLink, ...]
    partner_links: tuple[PartnerLink, ...]
    events: tuple[SynthEvent, ...]
    associations: tuple[SynthAssociation, ...]
    places: tuple[SynthPlace, ...]
    sources: tuple[SynthSource, ...]
    citations: tuple[SynthCitation, ...]

    def person(self, person_id: str) -> SynthPerson:
        for person in self.people:
            if person.id == person_id:
                return person
        raise KeyError(person_id)

    def graph(self) -> FamilyGraph:
        """The kinship graph of the family."""
        return FamilyGraph(
            {person.id: person.sex for person in self.people},
            self.parent_links,
            self.partner_links,
        )

    def events_of(self, person_id: str) -> tuple[SynthEvent, ...]:
        return tuple(event for event in self.events if person_id in event.principals)

    def vital_events(self, person_id: str) -> tuple[VitalEvent, ...]:
        """The person's events as the living rule sees them (a citation is evidence)."""
        return tuple(
            VitalEvent(event.event_type, event.date, has_evidence=bool(event.citation_ids))
            for event in self.events_of(person_id)
        )

    def living_status(self, person_id: str) -> LivingStatus:
        return infer_living_status(self.vital_events(person_id), today=self.today)

    def godparent_links(self) -> tuple[GodparentLink, ...]:
        """Godparent associations as compadrazgo input (one link per godchild)."""
        by_id = {event.id: event for event in self.events}
        links: list[GodparentLink] = []
        for association in self.associations:
            if association.role is not AssociationRole.GODPARENT or association.occasion is None:
                continue
            for godchild in by_id[association.event_id].principals:
                links.append(GodparentLink(association.person_id, godchild, association.occasion))
        return tuple(links)


@dataclass(frozen=True, slots=True)
class SyntheticLexicon:
    """Every name and place the generator may use, for CI guards on fixtures."""

    given_names: frozenset[str]
    surnames: frozenset[str]
    particles: frozenset[str]
    nicknames: frozenset[str]
    place_names: frozenset[str]

    def covers(self, form: NameForm) -> bool:
        """True when every part of `form` comes from this lexicon."""
        surnames = [
            s for s in (form.apellido_paterno, form.apellido_materno, *form.extra_surnames) if s
        ]
        particles = [p for p in (form.particle_paterno, form.particle_materno) if p]
        usado = [form.nombre_usado] if form.nombre_usado else []
        return (
            all(name in self.given_names for name in (*form.given_names, *usado))
            and all(surname in self.surnames for surname in surnames)
            and all(particle in self.particles for particle in particles)
            and all(apodo in self.nicknames for apodo in form.apodos)
        )

    def covers_place(self, name: str) -> bool:
        """True for a lexicon place or one derived from it («Parroquia de Villa Imaginaria»)."""
        return name in self.place_names or any(
            name.endswith(f" {base}") for base in self.place_names
        )


def _given_names() -> frozenset[str]:
    pools = (
        name_data.MALE_CLASSIC, name_data.FEMALE_CLASSIC, name_data.MALE_CONTEMPORARY,
        name_data.FEMALE_CONTEMPORARY, name_data.MALE_MODERN, name_data.FEMALE_MODERN,
        name_data.MALE_COMPOUND, name_data.FEMALE_COMPOUND,
    )  # fmt: skip
    found = {name for pool in pools for name in pool}
    # The name used of a compound name is one of its words («Jesús» of «María de Jesús»).
    found.update(word for name in name_data.MALE_COMPOUND + name_data.FEMALE_COMPOUND
                 for word in name.split() if word[0].isupper())  # fmt: skip
    return frozenset(found)


def synthetic_lexicon() -> SyntheticLexicon:
    """Return the lexicon the generator draws from."""
    surnames = set(name_data.SURNAMES) | {s for _, s in name_data.PARTICLE_SURNAMES}
    place_names = set(place_data.MX_STATES) | set(place_data.US_STATES)
    place_names.update(place_data.COUNTRIES.values())
    place_names.update(name for _, name in place_data.FICTIONAL_LOCALITIES)
    place_names.update(place_data.FICTIONAL_US_LOCALITIES)
    place_names.update(place_data.BRACERO_CENTERS)
    place_names.update(place_data.BORDER_CROSSINGS)
    return SyntheticLexicon(
        given_names=_given_names(),
        surnames=frozenset(surnames),
        particles=frozenset(p for p, _ in name_data.PARTICLE_SURNAMES),
        nicknames=frozenset(
            nickname_display(short) for shorts in HYPOCORISTICS.values() for short in shorts
        ),
        place_names=frozenset(place_names),
    )
