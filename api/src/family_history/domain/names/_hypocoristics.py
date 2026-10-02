"""Mexican hipocorísticos (affectionate short forms of given names) and their lookup.

The map goes from a formal given name to the short forms families use. Lookups work in both
directions and ignore accents and case. A short form shared by several names («Beto» for
Alberto, Roberto and Humberto) returns all of them; the expansion stops there, so «Alberto»
never yields «Roberto».
"""

from __future__ import annotations

from types import MappingProxyType

from ._normalize import strip_accents

__all__ = ["HYPOCORISTICS", "given_name_variants"]

_RAW: dict[str, tuple[str, ...]] = {
    "jesus": ("chucho", "chuy", "chuchito"),
    "maria de jesus": ("chuy", "chuya"),
    "jose": ("pepe", "pepito", "chepe"),
    "jose maria": ("chema",),
    "francisco": ("pancho", "paco", "panchito", "paquito", "curro"),
    "guadalupe": ("lupe", "lupita"),
    "isabel": ("chabela", "chabelita", "isa"),
    "salvador": ("chava", "chavita"),
    "ignacio": ("nacho",),
    "concepcion": ("concha", "conchita", "chona"),
    "dolores": ("lola", "lolita"),
    "guillermo": ("memo",),
    "alberto": ("beto",),
    "roberto": ("beto",),
    "humberto": ("beto",),
    "antonio": ("tono", "tonio"),
    "antonia": ("tona",),
    "eduardo": ("lalo",),
    "enrique": ("quique",),
    "rosario": ("chayo", "charo"),
    "refugio": ("cuca", "cuquita", "cuco"),
    "alicia": ("licha",),
    "mercedes": ("meche",),
    "pilar": ("pili",),
    "gregorio": ("goyo",),
    "josefa": ("pepa", "chepa"),
    "teresa": ("tere",),
    "lorenzo": ("lencho",),
    "consuelo": ("chelo",),
    "fernando": ("nando",),
    "rafael": ("rafa",),
    "manuel": ("manolo",),
    "margarita": ("mago", "magos"),
    "socorro": ("coco",),
    "rodolfo": ("fito",),
    "adolfo": ("fito",),
}

#: Formal given name (accent-free, lower-case) to its short forms. Read-only.
HYPOCORISTICS: MappingProxyType[str, tuple[str, ...]] = MappingProxyType(_RAW)

_BY_SHORT: dict[str, set[str]] = {}
for _formal, _shorts in _RAW.items():
    for _short in _shorts:
        _BY_SHORT.setdefault(_short, set()).add(_formal)


def _key(name: str) -> str:
    return " ".join(strip_accents(name).split())


def given_name_variants(name: str) -> set[str]:
    """Return `name` and its known formal and short forms, accent-free and lower-case.

    `given_name_variants("Chuy")` → {"chuy", "chucho", "chuchito", "jesus", "maria de jesus",
    "chuya"}; `given_name_variants("Jesús")` → {"jesus", "chucho", "chuy", "chuchito"}.
    Unknown names return just themselves; blank input returns an empty set.
    """
    key = _key(name)
    if not key:
        return set()
    formals = set(_BY_SHORT.get(key, set()))
    if key in _RAW:
        formals.add(key)
    variants = {key}
    for formal in formals:
        variants.add(formal)
        variants.update(_RAW[formal])
    return variants
