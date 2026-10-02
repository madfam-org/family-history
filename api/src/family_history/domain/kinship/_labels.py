"""Spanish (es-MX) and English kinship terms, gendered by the relative's sex.

Gender-neutral wording (sex X or U): Spanish has no settled neutral morphology, and «-e»
forms («hije») are not used. The library writes the masculine and feminine endings together,
«primo/a hermano/a», «tío/a abuelo/a segundo/a»; for a parent it writes «progenitor/a» and
for a spouse «cónyuge», which are standard neutral words. English uses its neutral nouns
(parent, sibling, cousin, spouse) and «uncle/aunt», «nephew/niece» where none exists.

Generations beyond the named ones follow Spanish genealogical usage: «segundo abuelo» is a
bisabuelo, so six generations up is «quinto abuelo», seven «sexto abuelo», and so on;
English counts greats: «3rd great-grandfather» is five generations up.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._graph import Sex

__all__ = [
    "Terms",
    "ancestor_terms",
    "cousin_terms",
    "descendant_terms",
    "merge_es",
    "nephew_terms",
    "ordinal_en",
    "ordinal_es",
    "sibling_terms",
    "uncle_terms",
]


@dataclass(frozen=True, slots=True)
class Terms:
    """A kinship term in both languages and three genders (masculine, feminine, neutral)."""

    es_m: str
    es_f: str
    es_n: str
    en_m: str
    en_f: str
    en_n: str

    def pick(self, sex: Sex) -> tuple[str, str]:
        """Return `(label_es, label_en)` for a relative of `sex`."""
        if sex is Sex.MALE:
            return self.es_m, self.en_m
        if sex is Sex.FEMALE:
            return self.es_f, self.en_f
        return self.es_n, self.en_n

    def map_es(self, suffix_m: str, suffix_f: str) -> Terms:
        """Append Spanish words that agree in gender (e.g. «político»/«política»)."""
        es_m, es_f = f"{self.es_m} {suffix_m}", f"{self.es_f} {suffix_f}"
        return Terms(es_m, es_f, merge_es(es_m, es_f), self.en_m, self.en_f, self.en_n)


def merge_es(masculine: str, feminine: str) -> str:
    """Merge two Spanish forms word by word: «tío abuelo» + «tía abuela» → «tío/a abuelo/a»."""
    m_words, f_words = masculine.split(), feminine.split()
    if len(m_words) != len(f_words):
        return f"{masculine}/{feminine}"
    merged: list[str] = []
    for m_word, f_word in zip(m_words, f_words, strict=True):
        if m_word == f_word:
            merged.append(m_word)
        elif m_word[:-1] == f_word[:-1] and m_word.endswith("o") and f_word.endswith("a"):
            merged.append(f"{m_word}/a")
        else:
            merged.append(f"{m_word}/{f_word}")
    return " ".join(merged)


def terms(es_m: str, es_f: str, en_m: str, en_f: str, en_n: str, es_n: str = "") -> Terms:
    """Build `Terms`, deriving the neutral Spanish form unless one is given."""
    return Terms(es_m, es_f, es_n or merge_es(es_m, es_f), en_m, en_f, en_n)


_ORD_ES = ("", "primer", "segund", "tercer", "cuart", "quint", "sext", "séptim", "octav",
           "noven", "décim")  # fmt: skip


def ordinal_es(n: int, feminine: bool = False) -> str:
    """Spanish ordinal adjective after a noun: «segundo», «tercera», «11.º»."""
    if 2 <= n < len(_ORD_ES):
        return _ORD_ES[n] + ("a" if feminine else "o")
    return f"{n}.ª" if feminine else f"{n}.º"


def ordinal_en(n: int) -> str:
    """English ordinal: 1st, 2nd, 3rd, 4th, 11th, 21st."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


_ORD_WORDS_EN = ("", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
                 "ninth", "tenth")  # fmt: skip


def _cousin_en(degree: int) -> str:
    word = _ORD_WORDS_EN[degree] if degree < len(_ORD_WORDS_EN) else ordinal_en(degree)
    return f"{word} cousin"


def _greats(count: int) -> str:
    """English «great-» prefixes: 0 → "", 1 → "great-", 2 → "great-great-", 3 → "3rd great-"."""
    if count <= 0:
        return ""
    if count <= 2:
        return "great-" * count
    return f"{ordinal_en(count)} great-"


_ANCESTOR_ES = {2: "abuel", 3: "bisabuel", 4: "tatarabuel", 5: "trastatarabuel"}
_DESCENDANT_ES = {2: "niet", 3: "bisniet", 4: "tataraniet", 5: "trastataraniet"}


def _generation_es(stems: dict[int, str], noun: str, n: int, feminine: bool) -> str:
    ending = "a" if feminine else "o"
    if n in stems:
        return stems[n] + ending
    return f"{ordinal_es(n - 1, feminine)} {noun}{ending}"


def ancestor_terms(generations: int) -> Terms:
    """Direct ancestor `generations` up (1 = parent)."""
    if generations == 1:
        return terms("padre", "madre", "father", "mother", "parent", es_n="progenitor/a")
    es_m = _generation_es(_ANCESTOR_ES, "abuel", generations, False)
    es_f = _generation_es(_ANCESTOR_ES, "abuel", generations, True)
    greats = _greats(generations - 2)
    return terms(es_m, es_f, f"{greats}grandfather", f"{greats}grandmother",
                 f"{greats}grandparent")  # fmt: skip


def descendant_terms(generations: int) -> Terms:
    """Direct descendant `generations` down (1 = child)."""
    if generations == 1:
        return terms("hijo", "hija", "son", "daughter", "child")
    es_m = _generation_es(_DESCENDANT_ES, "niet", generations, False)
    es_f = _generation_es(_DESCENDANT_ES, "niet", generations, True)
    greats = _greats(generations - 2)
    return terms(es_m, es_f, f"{greats}grandson", f"{greats}granddaughter",
                 f"{greats}grandchild")  # fmt: skip


def sibling_terms(half: bool) -> Terms:
    if half:
        return terms("medio hermano", "media hermana", "half-brother", "half-sister",
                     "half-sibling")  # fmt: skip
    return terms("hermano", "hermana", "brother", "sister", "sibling")


def _with_ordinal(base: Terms, degree: int) -> Terms:
    if degree < 2:
        return base
    es_m = f"{base.es_m} {ordinal_es(degree)}"
    es_f = f"{base.es_f} {ordinal_es(degree, True)}"
    return Terms(es_m, es_f, merge_es(es_m, es_f), base.en_m, base.en_f, base.en_n)


def _removed(count: int) -> str:
    if count == 0:
        return ""
    if count == 1:
        return " once removed"
    if count == 2:
        return " twice removed"
    return f" {count} times removed"


def uncle_terms(up: int, down: int) -> Terms:
    """Alter is in an older generation on a collateral line: tío, tío abuelo, tío segundo…

    `up` ≥ 2 is ego's distance to the common ancestor, `down` ≥ 1 alter's, `up > down`.
    """
    gen_diff = up - down
    if gen_diff == 1:
        es_m, es_f = "tío", "tía"
    else:
        ancestor = ancestor_terms(gen_diff)
        es_m, es_f = f"tío {ancestor.es_m}", f"tía {ancestor.es_f}"
    base_es = _with_ordinal(terms(es_m, es_f, "", "", ""), down)
    if down == 1:
        greats = _greats(gen_diff - 1)
        en = (f"{greats}uncle", f"{greats}aunt", f"{greats}uncle/aunt")
    else:
        en = (f"{_cousin_en(down - 1)}{_removed(gen_diff)}",) * 3
    return Terms(base_es.es_m, base_es.es_f, base_es.es_n, *en)


def nephew_terms(up: int, down: int) -> Terms:
    """Alter is in a younger generation on a collateral line: sobrino, sobrino nieto…

    `up` ≥ 1 is ego's distance to the common ancestor, `down` ≥ 2 alter's, `down > up`.
    """
    gen_diff = down - up
    if gen_diff == 1:
        es_m, es_f = "sobrino", "sobrina"
    else:
        descendant = descendant_terms(gen_diff)
        es_m, es_f = f"sobrino {descendant.es_m}", f"sobrina {descendant.es_f}"
    base_es = _with_ordinal(terms(es_m, es_f, "", "", ""), up)
    if up == 1:
        greats = _greats(gen_diff - 1)
        en = (f"{greats}nephew", f"{greats}niece", f"{greats}nephew/niece")
    else:
        en = (f"{_cousin_en(up - 1)}{_removed(gen_diff)}",) * 3
    return Terms(base_es.es_m, base_es.es_f, base_es.es_n, *en)


def cousin_terms(generations: int) -> Terms:
    """Same-generation cousins whose common ancestor is `generations` ≥ 2 up."""
    degree = generations - 1
    if degree == 1:
        base = terms("primo hermano", "prima hermana", "", "", "")
    else:
        base = _with_ordinal(terms("primo", "prima", "", "", ""), degree)
    en = _cousin_en(degree)
    return Terms(base.es_m, base.es_f, base.es_n, en, en, en)
