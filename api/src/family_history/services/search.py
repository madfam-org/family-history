"""People search over `person.search_tokens`.

The query is split into words. Each word is folded with `domain.names.normalize_for_search` and
expanded with `domain.names.given_name_variants` (hipocorísticos both ways, so «Chucho» finds
Jesús and «Jesús» finds Chucho). A person matches when every word matches one of their tokens:

- exactly (rank 0),
- through a variant (rank 1; a multi-word variant such as «José María» needs all its words),
- or as a prefix (rank 2).

The person's rank is the sum over the words, so exact hits come first, then variants, then
prefixes; ties fall back to the surname order. `search_tokens` is space-padded (` a b `), which
makes `LIKE '% a %'` an exact token and `LIKE '% a%'` a prefix; the trigram index on the column
(when `pg_trgm` exists) serves both.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, case, literal, or_

from family_history.domain.names import given_name_variants, normalize_for_search
from family_history.models import Person
from family_history.services.names import escape_like

MAX_WORDS = 8
RANK_EXACT = 0
RANK_VARIANT = 1
RANK_PREFIX = 2


@dataclass(frozen=True)
class WordPlan:
    token: str
    variants: tuple[tuple[str, ...], ...]


def plan(query: str | None) -> list[WordPlan]:
    """Fold and expand the query; words that fold to nothing («y», «e») are dropped."""
    words: list[WordPlan] = []
    for word in (query or "").split():
        folded = normalize_for_search(word).split()
        if not folded:
            continue
        if len(folded) > 1:  # an abbreviation that expanded («Ma.» → maría): no variants
            words.extend(WordPlan(token, ()) for token in folded)
            continue
        token = folded[0]
        variants: set[tuple[str, ...]] = set()
        for variant in given_name_variants(word):
            tokens = tuple(normalize_for_search(variant).split())
            if tokens and tokens != (token,):
                variants.add(tokens)
        words.append(WordPlan(token, tuple(sorted(variants))))
    return words[:MAX_WORDS]


def _exact(token: str) -> ColumnElement[bool]:
    return Person.search_tokens.like(f"% {escape_like(token)} %", escape="\\")


def _prefix(token: str) -> ColumnElement[bool]:
    return Person.search_tokens.like(f"% {escape_like(token)}%", escape="\\")


def _variant(tokens: tuple[str, ...]) -> ColumnElement[bool]:
    return and_(*(_exact(token) for token in tokens))


@dataclass(frozen=True)
class SearchSql:
    where: ColumnElement[bool]
    rank: ColumnElement[int]


def compile_search(words: list[WordPlan]) -> SearchSql | None:
    """The match condition and the rank expression, or None for an empty query."""
    if not words:
        return None
    conditions: list[ColumnElement[bool]] = []
    ranks: list[ColumnElement[int]] = []
    for word in words:
        exact = _exact(word.token)
        variant = or_(*(_variant(v) for v in word.variants)) if word.variants else None
        prefix = _prefix(word.token)
        options = [exact, prefix] if variant is None else [exact, variant, prefix]
        conditions.append(or_(*options))
        whens: list[tuple[ColumnElement[bool], int]] = [(exact, RANK_EXACT)]
        if variant is not None:
            whens.append((variant, RANK_VARIANT))
        ranks.append(case(*whens, else_=literal(RANK_PREFIX)))
    total: ColumnElement[int] = ranks[0]
    for rank in ranks[1:]:
        total = total + rank
    return SearchSql(where=and_(*conditions), rank=total)
