"""Pure genealogy domain library: stdlib only, no I/O, no clock reads.

The semantic core the API, the GEDCOM engine and the UI share:

- `dates`: the GEDCOM 7 `DateValue` grammar, bounds, Spanish/English display, Spanish input.
- `names`: the Mexican name model, display styles, search folding, hipocorísticos.
- `living`: living-status inference (the 110-year rule) and private-by-default.
- `sensitivity`: LFPDPPP sensitivity classes and the consent rule.
- `events`: event types, GEDCOM 7 tags and association roles.
- `kinship`: relationship labels between two people in a family graph.
- `compadrazgo`: derived padrino, ahijado and compadre relations.
- `synth`: the deterministic synthetic family generator and its lexicon.

Everything listed in `__all__` is public and stable within v1.
"""

from .compadrazgo import (
    CompadrazgoRelation,
    CompadrazgoRole,
    GodparentLink,
    Occasion,
    compadrazgo,
)
from .dates import (
    Calendar,
    CalendarDate,
    DateBounds,
    DateBoundsError,
    DateKind,
    DateParseError,
    DateValue,
    UnsupportedCalendarError,
    canonicalize_date_value,
    format_date_value,
    humanize_en,
    humanize_es,
    parse_date_value,
    parse_user_date_es,
)
from .events import (
    AssociationRole,
    EventSpec,
    EventType,
    event_spec,
    event_type_from_gedcom,
    role_from_gedcom,
)
from .kinship import (
    FamilyGraph,
    Kinship,
    KinshipKind,
    ParentLink,
    PartnerLink,
    PartnerStatus,
    Pedigree,
    Sex,
    kinship,
)
from .living import (
    DEFAULT_LIVING_WINDOW_YEARS,
    LivingAssessment,
    LivingBasis,
    LivingStatus,
    VitalEvent,
    assess_living,
    infer_living_status,
    is_private_by_default,
)
from .names import (
    DisplayStyle,
    NameForm,
    NameType,
    SurnameOrder,
    display_name,
    given_name_variants,
    normalize_for_search,
)
from .sensitivity import FactKind, Sensitivity, default_sensitivity, requires_consent_to_share
from .synth import SyntheticFamily, SyntheticLexicon, generate_family, synthetic_lexicon

__all__ = [
    "DEFAULT_LIVING_WINDOW_YEARS",
    "AssociationRole",
    "Calendar",
    "CalendarDate",
    "CompadrazgoRelation",
    "CompadrazgoRole",
    "DateBounds",
    "DateBoundsError",
    "DateKind",
    "DateParseError",
    "DateValue",
    "DisplayStyle",
    "EventSpec",
    "EventType",
    "FactKind",
    "FamilyGraph",
    "GodparentLink",
    "Kinship",
    "KinshipKind",
    "LivingAssessment",
    "LivingBasis",
    "LivingStatus",
    "NameForm",
    "NameType",
    "Occasion",
    "ParentLink",
    "PartnerLink",
    "PartnerStatus",
    "Pedigree",
    "Sensitivity",
    "Sex",
    "SurnameOrder",
    "SyntheticFamily",
    "SyntheticLexicon",
    "UnsupportedCalendarError",
    "VitalEvent",
    "assess_living",
    "canonicalize_date_value",
    "compadrazgo",
    "default_sensitivity",
    "display_name",
    "event_spec",
    "event_type_from_gedcom",
    "format_date_value",
    "generate_family",
    "given_name_variants",
    "humanize_en",
    "humanize_es",
    "infer_living_status",
    "is_private_by_default",
    "kinship",
    "normalize_for_search",
    "parse_date_value",
    "parse_user_date_es",
    "requires_consent_to_share",
    "role_from_gedcom",
    "synthetic_lexicon",
]
