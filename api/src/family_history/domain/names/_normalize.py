"""Search normalization for names written the many ways Mexican records write them.

`normalize_for_search` maps spellings that sound alike in Mexican Spanish to one key, so a
search for «Ximena Mejía Vázquez» also finds «Jimena Mexía Velásquez»-style variants. The
result is a matching key, never something to show a person. It is idempotent.

Steps, in order:

1. Lower-case; strip diacritics (á→a, ü→u, ñ→n).
2. Expand unambiguous record abbreviations: «Ma.» → maria, «Gpe.» → guadalupe,
   «Fco.» → francisco, «Fca.» → francisca, «Jph.»/«Jse.» → jose, «Ant.» → antonio,
   «Mnel.» → manuel, «Ma. de Jesús» → maria de jesus. The period is required: bare «Ma» is a
   surname in Chinese-Mexican families and stays as written. Single initials such as «J.» stay
   initials (José, Juan, Jesús and Javier are all common), since guessing would merge people.
3. Drop the surname joiners «y» and «e» («Pérez y González» matches «Pérez González») and
   turn remaining punctuation into spaces; collapse whitespace.
4. Fold each word: silent leading h (Hernández/Ernández); ll→y (yeísmo); final y→i
   (Godoy/Godoi); qu before e/i → k, c before e/i → s, other c → k (seseo; Carla/Karla);
   g before e/i → j (Giménez/Jiménez); z→s; x→j (Ximena/Jimena, Mexía/Mejía); v→b.
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["ABBREVIATIONS", "fold_word", "normalize_for_search", "strip_accents"]

#: Record abbreviations expanded by `normalize_for_search` (keys are accent-free, lower-case,
#: with their period).
ABBREVIATIONS: dict[str, str] = {
    "ma.": "maria",
    "gpe.": "guadalupe",
    "fco.": "francisco",
    "fca.": "francisca",
    "jph.": "jose",
    "jse.": "jose",
    "ant.": "antonio",
    "mnel.": "manuel",
}

_JOINERS = frozenset({"y", "e"})
_PUNCT = re.compile(r"[^\w\s]|_")
_TOKEN = re.compile(r"[a-z]+\.|[^\s]+")


def strip_accents(text: str) -> str:
    """Lower-case `text` and remove diacritics, keeping letters and spacing."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return unicodedata.normalize("NFKC", stripped).lower()


def fold_word(word: str) -> str:
    """Apply the orthographic folds of step 4 to one accent-free lower-case word."""
    folded = word.lstrip("h") or word
    folded = folded.replace("ll", "y")
    if len(folded) > 1 and folded.endswith("y"):
        folded = folded[:-1] + "i"
    folded = re.sub(r"qu(?=[ei])", "k", folded)
    folded = re.sub(r"c(?=[ei])", "s", folded)
    folded = re.sub(r"c(?!h)", "k", folded)
    folded = re.sub(r"g(?=[ei])", "j", folded)
    return folded.replace("z", "s").replace("x", "j").replace("v", "b")


def normalize_for_search(text: str) -> str:
    """Return the search key of `text` (see the module docstring for the exact rules)."""
    words: list[str] = []
    for raw in strip_accents(text).split():
        for token in _TOKEN.findall(raw):
            expanded = ABBREVIATIONS.get(token)
            if expanded is not None:
                words.extend(expanded.split())
                continue
            words.extend(_PUNCT.sub(" ", token).split())
    folded = (fold_word(word) for word in words if word not in _JOINERS)
    # Filtering again keeps the key idempotent: «he» folds to «e», a joiner on the next pass.
    return " ".join(word for word in folded if word not in _JOINERS)
