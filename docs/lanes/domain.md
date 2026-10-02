# Lane DOM: pure genealogy domain library

> Last Updated: 2026-10-01

Lane DOM built `family_history.domain` (`api/src/family_history/domain/`). It is the semantic
core that the API, the GEDCOM engine and the UI share. It uses only the standard library: no
I/O, no database, no network, and no clock reads (`today` is always passed in). Tests enforce
this.

## Status

Done. Every module listed below is implemented and tested. Nothing persists the results yet:
the API lane owns persistence, and the CLI owns `seed-synth`.

## Public API

Everything below is re-exported from `family_history.domain` (see its `__all__`). The
submodules also export their helpers.

### `domain.dates`: GEDCOM 7.0 dates

| Signature | What it does |
|---|---|
| `parse_date_value(text: str, phrase: str \| None = None) -> DateValue` | Strict parse of the GEDCOM 7 `DateValue` grammar. Raises `DateParseError` (`.reason`, `.text`, `.code`). |
| `format_date_value(value: DateValue) -> str` | Canonical GEDCOM 7 text. Guarantees `format(parse(s)) == canonicalize_date_value(s)`. |
| `canonicalize_date_value(text: str) -> str` | `format(parse(text))`. |
| `parse_calendar_date(text: str) -> CalendarDate` | One `date`, with no keyword. |
| `humanize_es(value, *, include_phrase=False) -> str` | Returns «15 de marzo de 1923», «hacia 1891», «antes del 15 de marzo de 1900», «entre 1890 y 1895», «de 1910 a 1920», and so on. |
| `humanize_en(value, *, include_phrase=False) -> str` | Returns "15 March 1923", "about 1891", "between 1890 and 1895". |
| `parse_user_date_es(text: str) -> DateValue` | A forgiving parser for what Mexican users type. It never guesses. Ambiguous input raises `DateParseError` with `code == "ambiguous_date"`. |
| `DateValue(kind, first, second, phrase, original)` | Exposes `.earliest` and `.latest` (proleptic Gregorian `date \| None`), `.bounds(approx_years=5)`, `.jdn_bounds(approx_years=5)` and `.format()`. |
| `CalendarDate(year, month, day, calendar, bce)` | Exposes `.jdn_bounds(widen_years=0)`, `.precision` and `.format()`. |
| `DateKind` | `EMPTY`, `DATE`, `ABT`, `CAL`, `EST`, `BEF`, `AFT`, `BET`, `FROM`, `TO`, `FROM_TO`. |
| `Calendar` | `GREGORIAN`, `JULIAN`, `FRENCH_R`, `HEBREW`. |
| Errors | `DateParseError`, `DateBoundsError` and its subclass `UnsupportedCalendarError`. All are `ValueError`s. |

### `domain.names`: Mexican names

| Signature | What it does |
|---|---|
| `NameForm(given_names, apellido_paterno, apellido_materno, particle_paterno, particle_materno, surname_joiner, extra_surnames, nombre_usado, apodos, name_type, lang, surname_order)` | Frozen and validated. `.nombre_de_pila`, `.surnames_text()`, `.sort_surname()`. |
| `display_name(form, style=DisplayStyle.FULL) -> str` | Styles are `FULL`, `FORMAL`, `SHORT` and `SORTING`. |
| `normalize_for_search(text: str) -> str` | The search key. It is idempotent. |
| `given_name_variants(name: str) -> set[str]` | The hipocorístico lookup. It works in both directions and ignores accents. |
| `NameType` | `birth`, `baptism`, `civil`, `married`, `aka`, `religious`, `immigrant`, `indigenous`, `professional`, with `.label_es`, `.label_en` and `.gedcom_type -> (TYPE, PHRASE \| None)`. |
| `SurnameOrder` | `paterno_first`, `materno_first` and `pt_BR`. |
| Also exported | `HYPOCORISTICS` (read-only), `nickname_display`, `ABBREVIATIONS`, `strip_accents`, `fold_word`, `PARTICLES`. |

### `domain.living`: living status

| Signature | What it does |
|---|---|
| `assess_living(events: Iterable[VitalEvent], *, today: date, window_years=110, approx_years=5) -> LivingAssessment` | Returns `.status`, `.basis`, `.latest_birth` and `.private_by_default`. |
| `infer_living_status(...) -> LivingStatus` | Returns only the status. |
| `is_private_by_default(status: LivingStatus) -> bool` | True for `LIVING` and `UNKNOWN`. |
| `VitalEvent(event_type, date=None, has_evidence=False)` | The input record. |
| `LivingStatus` | `living`, `deceased`, `presumed_deceased`, `unknown`. `.contract_value` maps the status onto the v1 API's three values. |

### `domain.sensitivity`

| Signature | What it does |
|---|---|
| `Sensitivity` | `none`, `religion`, `health`, `genetic`, `ethnicity`, `sexual`, `political`, with es/en labels. |
| `default_sensitivity(kind: EventType \| FactKind) -> Sensitivity` | Sacramental events are `religion`. `FactKind.CAUSE_OF_DEATH` and `MEDICAL_NOTE` are `health`. |
| `requires_consent_to_share(living_status, sensitivity) -> bool` | True for a sensitive fact about someone `LIVING` or `UNKNOWN`. |

### `domain.events`

| Signature | What it does |
|---|---|
| `EventType` | Covers BIRT, BAPM, CHR, CONF, FCOM, MARR (generic, civil, religious), DIV, DEAT, BURI, CREM, EMIG, IMMI, NATU, RESI, OCCU, EDUC, and EVEN typed «XV años», «Contrato bracero», «Cruce fronterizo» and `OTHER`. Each has `.gedcom_tag`, `.gedcom_type`, `.label_es`, `.label_en`, `.is_sacramental`, `.is_family_event`, `.is_death_evidence` and `.bounds_birth`. |
| `event_type_from_gedcom(tag: str, type_text: str \| None = None) -> EventType` | Maps a tag and TYPE back to an event type. TYPE matching ignores accents and case. |
| `AssociationRole` | `GODP`, `WITN`, `OFFICIATOR`, `CLERGY` and `OTHER`. `.gedcom_role(phrase=None) -> (ROLE, PHRASE)`; `OTHER` requires a phrase. |
| `role_from_gedcom(value: str) -> AssociationRole` | Maps a ROLE payload back to a role. |

### `domain.kinship`

| Signature | What it does |
|---|---|
| `FamilyGraph(sexes: Mapping[str, Sex], parent_links=(), partner_links=())` | The family graph. |
| `ParentLink(parent, child, pedigree=Pedigree.BIRTH)` | `Pedigree` is `birth`, `adopted`, `foster` or `step`. |
| `PartnerLink(a, b, status=PartnerStatus.MARRIED)` | `PartnerStatus` is `married`, `union_libre`, `partner`, `separated` or `divorced`. |
| `kinship(graph, ego, alter, max_depth=8) -> Kinship \| None` | Says what `alter` is to `ego`. |
| `Kinship` | Fields `kind` (`self`, `partner`, `blood`, `foster`, `step`, `in_law`), `label_es`, `label_en`, `up`, `down`, `half: bool \| None`, `adoptive`, `partner_status` and `via`. |
| `Sex` | `M`, `F`, `X`, `U`, matching the v1 `PersonSummary.sex`. |

### `domain.compadrazgo`

| Signature | What it does |
|---|---|
| `GodparentLink(godparent, godchild, occasion)` | The only stored fact. |
| `Occasion` | `bautizo`, `confirmacion`, `primera_comunion`, `boda`, `xv_anos`, `presentacion`, with labels and `.event_type`. |
| `compadrazgo(graph, godparents, ego, alter=None) -> list[CompadrazgoRelation]` | Derives padrino/madrina, ahijado/ahijada and compadre/comadre. Each relation has `role`, `alter`, `occasion`, `godchild`, `label_es` and `label_en`. |

### `domain.synth`: synthetic families

| Signature | What it does |
|---|---|
| `generate_family(seed: int, generations: int = 4, today: date = DEFAULT_TODAY) -> SyntheticFamily` | Builds 3 to 6 generations and is deterministic. |
| `SyntheticFamily` | Holds `people`, `parent_links`, `partner_links`, `events`, `associations`, `places`, `sources` and `citations` as tuples of plain dataclasses. Also offers `.graph()`, `.godparent_links()`, `.events_of(id)`, `.vital_events(id)`, `.living_status(id)` and `.person(id)`. |
| `synthetic_lexicon() -> SyntheticLexicon` | Exposes `.given_names`, `.surnames`, `.particles`, `.nicknames`, `.place_names`, `.covers(form)` and `.covers_place(name)`. Use it for the CI fixture guard. |

The lexicon data lives in `domain/data/names.py` and `domain/data/places.py` as plain tuples, so no file I/O is needed.

## Design decisions

### Dates

**Canonical form.**
- Keywords are upper case and separated by single spaces.
- Days and years lose their leading zeros.
- An explicit `GREGORIAN` is dropped, because it is the default.

**Strictness.**
- The parser accepts lower case and extra spaces.
- It rejects GEDCOM 5.5.1 syntax and says why. That covers dual years (`1750/51`), `@#DJULIAN@` escapes, `INT … (text)`, `ABOUT` and `BC`.
- It also rejects extension calendars and epochs.
- `BET x AND y` and `FROM x TO y` must be in order whenever both ends convert to day numbers.

**Bounds.**
- Bounds are inclusive, following GEDCOM 7 semantics: `BEF x` means no later than the end of x, and `AFT x` means no earlier than its start.
- `ABT`, `CAL` and `EST` widen by ±5 calendar years. The margin is configurable.
- Bounds are computed through Julian Day Numbers, so Julian dates convert correctly and BCE dates still sort (`jdn_bounds`).
- `.earliest` and `.latest` raise `DateBoundsError` outside the range of `datetime.date`.
- French Republican and Hebrew dates parse and round-trip, but raise `UnsupportedCalendarError` for bounds.

**User input.**
- All-numeric dates are read day/month/year (es-MX). A month above 12 is an error that suggests the month name; the parts are never swapped.
- Two-digit years are rejected.
- «1890-1895» is rejected because it could mean a range or a period.
- A weekday, if given, must match the date.

**Display.** Spanish adds the article before a full date: «antes del 15 de marzo de 1900», «del 15 de marzo de 1910 al 2 de abril de 1920». Spanish display text always parses back through `parse_user_date_es`, and a property test checks this.

### Names

**Never assume a married name.**
- No function derives a married name.
- A woman keeps both of her surnames.
- A `MARRIED` form exists only when a record states one. The synthetic generator adds one only for a US immigration record.

**Particles** are stored apart from their surname. `SORTING` follows the RAE convention, «Garza y Treviño, Ignacio de la». Note that many Mexican lists file «De la Garza» under D; `sort_surname()` gives the surname proper either way.

**Surname order.**
- `materno_first` (SCJN Amparo en Revisión 208/2016) writes the mother's surname first and sorts by it.
- `pt_BR` writes mother then father but sorts by the last (paternal) surname.

**`normalize_for_search`** applies these steps, documented in the module:
1. Lower case and strip diacritics.
2. Expand abbreviations: «Ma.», «Gpe.», «Fco.», «Fca.», «Jph.», «Jse.», «Ant.» and «Mnel.».
   - The period is required, because bare «Ma» is a surname in Chinese-Mexican families.
   - Single initials such as «J.» are never expanded, since José, Juan, Jesús and Javier are all common.
3. Drop the joiners «y» and «e».
4. Fold spellings that sound alike:
   - silent leading h;
   - ll→y (yeísmo);
   - final y→i;
   - qu/c before e or i → k or s, and other c → k (so «ch» survives);
   - g before e or i → j;
   - z→s, x→j, v→b.

The fold is idempotent (a property test checks this) and is a matching key only, never shown to anyone.

**Hipocorísticos.**
- The map runs from formal name to short forms and works in both directions.
- A shared short form («Beto») returns all of its formal names, and expansion stops there, so «Alberto» never yields «Roberto».

### Living status and privacy

**The 110-year rule.**
- A person is `deceased` only with an evidenced death, burial or cremation.
- Otherwise, if the latest possible birth falls within 110 years of `today` (inclusive), the person is `living`.
- If every possible birth date is older than that, the status is `presumed_deceased`.
- With no birth bound at all, the status is `unknown`.
- The latest-birth bound comes from the birth, baptism or christening, whichever is tightest.
- Approximate dates use their widened bounds, which errs toward privacy.
- Under `AFT x` the latest bound is open: the person is `living` if x falls within the window and `unknown` otherwise.

**Evidence.** `VitalEvent.has_evidence` defaults to False. A death that no source backs does not make anyone deceased (docs/PRIVACY.md §1).

**Consent.** `requires_consent_to_share` is true for any sensitive class about someone `living` or `unknown` (LFPDPPP Art. 2 VI and Art. 8; PRIVACY.md §2–3).

### Kinship

**Precedence.** Rules are tried in this order:
1. self;
2. partner (a spouse who is also a cousin is called a spouse);
3. blood or full adoption, by lowest common ancestor;
4. explicit foster and step links;
5. step relations derived through a partner;
6. affinity through one partner;
7. concuño and consuegro.

**Adoption** counts as full kinship (adopción plena), with an `adoptive` flag. The direct labels say «padre adoptivo» and «hija adoptiva».

**Foster and step links** relate only the two people they connect.

**Half siblings.** `half` is True only when both people's other parents are known and differ; otherwise it is None (unknown). Labels show half only for siblings («medio hermano»), which matches Spanish usage. Elsewhere the flag carries it.

**Generations.**
- Up to five generations use the named terms: abuelo, bisabuelo, tatarabuelo, trastatarabuelo.
- Beyond that, labels follow Spanish genealogical usage: «quinto abuelo» is six generations up, «sexto abuelo» seven, and «quinto nieto» runs the other way.
- English counts greats: «3rd great-grandfather».

**Collateral lines.** Spanish uses «tío/sobrino + ordinal»: «tío segundo» is a parent's first cousin, «sobrino segundo» is a first cousin's child, «tío abuelo segundo», «sobrino nieto segundo». English uses «Nth cousin N times removed».

**Gender-neutral labels for X and U.**
- The «-e» forms are not used.
- The library writes both endings: «primo/a hermano/a», «tío/a abuelo/a segundo/a».
- It uses established neutral nouns where they exist: «progenitor/a» for a parent and «cónyuge» for a spouse.
- English uses its neutral nouns (parent, sibling, cousin, spouse) and «uncle/aunt» where none exists.

**Affinity labels.**
- Named terms: suegro, yerno/nuera, cuñado, concuño, consuegro.
- Any other relative by marriage is «<term> político/a» ("… by marriage").

### Compadrazgo

- Only `GodparentLink` is stored. Padrino/ahijado and compadre/comadre are derived, never stored (ARCHITECTURE §Data model).
- Compadres are the godparent and the godchild's parents by birth or adoption. Foster parents are not compadres.
- For a wedding, the padrinos sponsor each spouse, so they become compadres of both spouses' parents.

### Synthetic data

**Determinism.**
- The generator uses one seeded `random.Random` and no global state.
- `today` defaults to a fixed date, so fixtures never drift with the calendar.

**Places.**
- States and countries are real.
- Every locality, parish, cemetery, registry office, bracero centre and border crossing is invented. Each name carries a word such as Ficción, Ejemplo, Ensayo, Supuesto, Imaginaria or Simulado.
- `SynthPlace.fictional` marks these.

**Sources** are «… (sintético)» repositories. Citations take the forms «Libro 12, foja 34, partida 210», «Acta 125, foja 117, libro 1», «Expediente 12345» and «Entrevista grabada, minuto 12».

**Coverage of the model.** Across seeds the generator produces:
- civil and religious marriages, unión libre and divorce;
- bracero contracts (1942–1964 only) and border crossings;
- immigration, naturalization, residence, schooling and work;
- XV años;
- deaths with causes (health-sensitive) and burials;
- a few undocumented deaths, which exercise the evidence rule;
- living young generations;
- presumed-deceased elders.

## Tests and coverage

**Gates.** `ruff check .`, `mypy src` (strict) and `pytest -q`: **518 tests pass**. Line coverage of `family_history.domain` is 99%. The uncovered lines are defensive guards in the generator, plus one validation branch in each of `dates/_model.py`, `dates/_user_input.py`, `kinship/_compute.py` and `kinship/_labels.py`.

**Property tests (hypothesis).**
- Dates:
  - `parse(format(v)) == v` for random date values across every kind and calendar;
  - canonicalization is idempotent and ignores case, spacing and zeros;
  - bounds are ordered, and a wider approximation margin never narrows them;
  - Gregorian JDN agrees with `datetime`;
  - the Julian lag is 10 days (1583–1699) and 13 days (1900–2100);
  - Spanish display text parses back to the same value.
- Names: search normalization is idempotent, ASCII-only, and ignores case and accents.
- Living status: exact births split cleanly at the 110-year boundary, and an evidenced death always wins.
- Kinship: direct and collateral distances mirror each other in both directions.
- Synthetic generator: any seed and generation count produce a consistent family.

**Known conversions.** Julian→Gregorian is checked against well-known dates: the 1582 switch, Shakespeare's death, Newton's and Washington's births, Britain in 1752, Russia in 1918, 29 Feb 1700, and 1 Mar 2100.

**Package guards** (`test_domain_package.py`):
- imports are standard library only;
- no `open`, `today`, `now`, `getenv` or socket calls;
- every file is under 600 lines;
- `__all__` is complete.

## Contract requests

1. **`PersonSummary.living_status` needs `presumed_deceased`.** PRIVACY.md §1 makes a person born more than 110 years ago, with no death evidence, *not* private. The v1 enum (`living|deceased|unknown`) cannot say "not proven dead but not private".
   - Proposal: add `presumed_deceased` to the API enum and UI copy, «Probablemente finado/a».
   - Until then, `LivingStatus.contract_value` maps it to `deceased`.
   - Visibility must always come from `is_private_by_default`, never from the enum value.
2. **Definition of death evidence (API lane).** Pass `VitalEvent.has_evidence=True` only for an accepted death, burial or cremation assertion with at least one citation. The domain cannot see assertion status.
3. **Relationship `qualifier` vocabulary (ARCHITECTURE v1 `POST …/relationships`).** Proposal:
   - parent-child: the `Pedigree` values `birth`, `adopted`, `foster`, `step`;
   - unions: the `PartnerStatus` values `married`, `union_libre`, `partner`, `separated`, `divorced`;
   - civil and religious marriage stay events (`civil_marriage`, `religious_marriage`), not qualifiers.
4. **`EventBrief.date_value`.** It is the output of `format_date_value` (canonical GEDCOM 7). UI display should call `humanize_es` or `humanize_en`, and input should go through `parse_user_date_es`.
5. **GEDCOM lane.** `parse_date_value` is strict GEDCOM 7. The 5.5.1 importer must convert dual years, `@#D…@` escapes and `INT (…)` before parsing; the error messages name each case. Map `NAME.TYPE` with `NameType.gedcom_type`, events with `event_type_from_gedcom`, and roles with `AssociationRole.gedcom_role`.
6. **AGENTS.md doctrine 1 wording.**
   - It names the lexicon as living "in `family_history.domain.synth`". The data lives in `family_history.domain.data`; the accessor is `family_history.domain.synth.synthetic_lexicon()`.
   - The `seed-synth` CLI command (not this lane) should call `generate_family(seed, generations)`.
