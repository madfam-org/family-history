"""The Mexican name model, display styles, search normalization and hipocorísticos."""

from ._hypocoristics import HYPOCORISTICS, given_name_variants, nickname_display
from ._model import PARTICLES, DisplayStyle, NameForm, NameType, SurnameOrder, display_name
from ._normalize import ABBREVIATIONS, fold_word, normalize_for_search, strip_accents

__all__ = [
    "ABBREVIATIONS",
    "HYPOCORISTICS",
    "PARTICLES",
    "DisplayStyle",
    "NameForm",
    "NameType",
    "SurnameOrder",
    "display_name",
    "fold_word",
    "given_name_variants",
    "nickname_display",
    "normalize_for_search",
    "strip_accents",
]
