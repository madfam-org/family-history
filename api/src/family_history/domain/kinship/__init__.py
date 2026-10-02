"""Kinship between two people in a family graph, with Spanish and English labels."""

from ._compute import DEFAULT_MAX_DEPTH, Kinship, KinshipKind, kinship
from ._graph import FamilyGraph, ParentLink, PartnerLink, PartnerStatus, Pedigree, Sex
from ._labels import Terms, merge_es, ordinal_en, ordinal_es

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "FamilyGraph",
    "Kinship",
    "KinshipKind",
    "ParentLink",
    "PartnerLink",
    "PartnerStatus",
    "Pedigree",
    "Sex",
    "Terms",
    "kinship",
    "merge_es",
    "ordinal_en",
    "ordinal_es",
]
