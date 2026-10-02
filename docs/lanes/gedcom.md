# Lane GED: the GEDCOM engine

> Last Updated: 2026-10-01

Branch `feat/gedcom-engine`. The package is `family_history.gedcom`
(`api/src/family_history/gedcom/`). It is pure standard library: it has no third-party
dependencies, no network and no filesystem access, and it does not import
`family_history.domain`. User-facing behaviour and the extension tags are documented in
[docs/GEDCOM.md](../GEDCOM.md).

## Public API

Everything below can be imported from `family_history.gedcom` unless a submodule is named.

```python
# Reading
parse_gedcom7(data: bytes | str, *, strict: bool = False, max_depth: int = 128) -> ParseResult
#   ParseResult(document: GedcomDocument, structures: list[Structure],
#               diagnostics: list[Diagnostic], extension_tags: Counter[str]); .warnings
#   strict=True raises GedcomStrictError(diagnostics) listing every violation with line numbers.
import_gedcom551(data: bytes | str, *, max_depth: int = 128) -> ImportResult
#   ImportResult(document: GedcomDocument, report: ImportReport, structures: list[Structure])
#   ImportReport(source_version, source_product, encoding, declared_charset,
#                record_counts: dict[str, int], created_records: dict[str, int],
#                diagnostics: list[Diagnostic], extension_tags: dict[str, int],
#                renamed_xrefs: dict[str, str]); .warnings; .codes() -> Counter[str]

# Writing
write_gedcom7(document, *, line_ending: str = "\n", bom: bool = True) -> bytes
write_gedcom7_text(document, *, line_ending: str = "\n") -> str
write_gedcom551(document, *, line_ending: str = "\r\n", bom: bool = False) -> Export551
#   Export551(data: bytes, report: list[Diagnostic])

# GEDZIP (bytes or binary streams only)
build_gedzip(document, media: Mapping[str, bytes] | Callable[[str], bytes | None]) -> GedzipBuild
write_gedzip(gedcom: bytes, media: Mapping[str, bytes], *, compress_media: bool = False) -> bytes
read_gedzip(source: bytes | BinaryIO, *, limits: GedzipLimits | None = None) -> GedzipContents
iter_gedzip(source: bytes | BinaryIO, *, limits: GedzipLimits | None = None)
    -> Iterator[tuple[str, bytes]]          # gedcom.ged first; raises GedzipError
GedzipLimits(max_entries=20_000, max_entry_bytes=1 GiB, max_total_bytes=8 GiB,
             max_gedcom_bytes=512 MiB, max_ratio=200, max_name_length=1024)

# Model (family_history.gedcom.model and .model_parts)
GedcomDocument(header, submitters, individuals, families, sources, repositories, media,
               shared_notes, extension_records)
    .records(), .by_xref(), .individual(xref), .family(xref)
    .from_structures(roots) / .to_structures()
Header, Individual, Family, Source, Repository, Multimedia, SharedNote, Submitter
PersonalName, NamePiece, Event, Date, Place, Association, SourceCitation, Note, ...
#   Every typed class: .from_structure(Structure) and .to_structure(tag) -> Structure,
#   plus an `other: list[Structure]` holding everything it does not model.
Structure(tag, payload=None, pointer=None, children=[], xref=None, line=None)
    .first(tag), .all(tag), .text(tag), .add(tag, payload, pointer=...), .walk(), .copy()

# Diagnostics
Diagnostic(severity: Severity, code: str, message: str, line: int | None)
Severity.ERROR | WARNING | INFO
GedcomError > GedcomSyntaxError, GedcomStrictError, GedzipError

# Mexican mappings (family_history.gedcom.mexico): pure functions
MexicanName(given, paternal_surname, maternal_surname, nicknames, order, prefix, suffix,
            name_type)
name_to_structure(MexicanName) -> Structure;  name_from_structure(Structure) -> MexicanName
Godparent(pointer="@VOID@", phrase=None)
godparent_association(Godparent) -> Structure;  godparents_from_event(Structure) -> list
sacrament_event(Sacrament, *, date=None, place=None, godparents=(), subject_living=False)
event_structure(EventKind, *, date=None, place=None, label=None) -> Structure
event_kind(Structure) -> EventKind | None;  union_kind(Structure) -> EventKind | None
apply_sensitivity(Structure, classes, *, subject_living: bool) -> Structure  # returns a copy
sensitivity_of(Structure) -> frozenset[Sensitivity]
default_sensitivity(Structure) -> frozenset[Sensitivity]

# Extension registry (family_history.gedcom.extensions)
MADFAM_EXTENSIONS: dict[str, ExtensionTag]   # _FH_SURNAME_LINE, _FH_SURNAME_ORDER,
                                             # _FH_SENSITIVITY, _FH_EVENT_KIND
```

## Modules

| Module | Role |
|---|---|
| `lines.py` | Tokenizer and level builder; CR, LF and CR-LF; 7.0 and 5.5.1 dialects; tolerant repairs |
| `charsets.py`, `ansel.py` | 7.0 UTF-8/UTF-16 decoding; 5.5.1 `CHAR` handling; ANSEL best effort |
| `structure.py` | Generic `Structure` node |
| `typed.py` | Declarative typed-dataclass ⇄ `Structure` mapping (the lossless rules) |
| `model.py`, `model_parts.py` | Typed 7.0 records, substructures and `GedcomDocument` |
| `spec_grammar.py`, `spec.py` | The 7.0.18 structure grammar, verbatim from the spec, parsed into lookup tables |
| `datatypes.py` | Syntactic checks for payload types (dates stay strings) |
| `validate.py` | Spec-driven validation (strict errors or tolerant warnings) |
| `parse7.py` | 7.0 reader |
| `parse551.py`, `upgrade551.py`, `upgrade551_media.py`, `upgrade551_tables.py`, `dates551.py` | 5.5.1 reader and upgrade to 7.0 |
| `emit.py` | Line serializer (CONT; CONC at 255 for 5.5.1; `@` escaping) |
| `write7.py` | Deterministic 7.0 writer with `SCHMA` |
| `write551.py`, `downgrade551.py` | 5.5.1 writer and marked downgrade |
| `gedzip.py` | GEDZIP read and write with limits |
| `extensions.py` | MADFAM extension tags and URIs |
| `mexico.py` | Mexican mapping helpers |

Every file is under 600 lines. The largest is `spec_grammar.py` at 497.

## Decisions

* **The spec grammar is data, not code.** The validator runs on the specification's own
  `gedstruct` blocks (Apache-2.0, attributed in the module docstring), parsed at import. This
  covers every structure and cardinality in 7.0.18 without a hand-written table drifting from
  the spec. Upgrading to a later 7.0.x means replacing the text block.
* **Generic tree first, typed view second.** Everything is read into `Structure` trees. Typed
  dataclasses are built from them by declaration, and whatever a typed field cannot hold
  losslessly stays in `other`. When one structure of a tag does not fit its typed field, every
  structure with that tag goes to `other`, so same-tag order never changes. Name pieces are
  `NamePiece` objects, not strings, so `_FH_SURNAME_LINE` under a `SURN` stays in place.
* **Strict versus tolerant.** Both modes run the same checks. Strict mode raises
  `GedcomStrictError` with every violation. Tolerant mode records the same findings as warnings
  and never raises on malformed input; the property tests feed arbitrary bytes and text to both
  readers.
* **Dates stay strings.** Only the 7.0 date grammar is checked. The 5.5.1 upgrade normalizes
  spellings and moves anything unparseable into `PHRASE`; no calendar arithmetic happens here.
* **Dual years resolve to the new-style year** (`1750/51` becomes `1751`) with the original kept
  in `PHRASE`, following appendix A of the 7.0 specification.
* **RFN conversion follows the registry's prose,** not its example: `RFN xyz:123abc` becomes
  `EXID 123abc` with `TYPE https://gedcom.io/terms/v7/RFN#xyz`. The registry example has the two
  parts the other way round, which contradicts its own text. The 5.5.1 writer reverses the
  mapping exactly.
* **The 5.5.1 export is lossy but marked.** Constructs 5.5.1 lacks become underscore tags, and
  the export report lists each one. The exception is padrinos under an individual's event:
  they move up to `INDI.ASSO` with a `RELA` naming the event, because that is the form legacy
  tools display.
* **GEDZIP never touches the disk.** `iter_gedzip` streams validated entries so that the worker
  can write them to object storage. Names are validated before any byte is read, and sizes are
  counted during decompression.
* **Extension tags are prefixed `_FH_`** to avoid collisions with vendor tags. Their URIs are
  anchors in docs/GEDCOM.md on `main`.

## Tests

`api/tests/gedcom/` holds 164 tests, run with `pytest -q` (about 14 s locally, most of it in the
Hypothesis tests). Fixtures in `api/tests/fixtures/gedcom/` are hand-written and invent every
person:

* `familia-sintetica-7.ged` is a full-featured 7.0 file.
* `ancestry-like-551.ged`, `myheritage-like-551.ged`, `rootsmagic-like-551.ged` (UTF-8 with BOM
  and CR-LF) and `gramps-like-551-ansel.ged` (ANSEL, including one deliberately undefined byte)
  are shaped like those vendors' 5.5.1 exports, quirks included.

| File | Covers |
|---|---|
| `test_lines.py` | Terminators, BOMs, UTF-16, escapes, `CONT`/`CONC`, level jumps, orphans, garbage lines, banned characters, depth limit, line numbers |
| `test_tokenizer_hypothesis.py` | Arbitrary text and bytes never crash either reader; emit, tokenize and build is the identity for 7.0, and for 5.5.1 with `CONC` splitting |
| `test_parse7.py` | Typed model from the fixture; strict violations for every enumeration (SEX, ROLE, PEDI, RESN, QUAY, NAME.TYPE), dates, ages, times, pointers, cardinality, shape and schema; tolerant warnings |
| `test_roundtrip7.py` | parse7, write7 and parse7 give an equal document and byte-stable output; extension and unknown structures are lossless; `SCHMA` declarations; record order; vendor imports round-trip |
| `test_import551_vendors.py` | The four vendor-shaped files: counts, warnings, extension tags, xref renames and data |
| `test_upgrade551.py` | Date table, header rules, enumerations, ages, associations, `EXID`, events, aliases, coordinates, media shapes, file URLs, every character-set path, ANSEL |
| `test_write551.py` | Downgrade markings, `INT` dates, calendars, enumerations, identifiers, `CONC` at 255 without edge spaces, `@` doubling, determinism, re-import |
| `test_gedzip.py` | Round trip, determinism, percent-encoded names, missing media, `gedcom.ged` renaming, traversal names, symlinks, duplicates and case collisions, encryption, zip bombs (ratio, entry, total and `gedcom.ged` limits), lying headers, entry-count and name-length limits |
| `test_mexico.py` | Two surnames in both orders, reading names without extensions, padrinos, unions, XV años, bracero and border events, sensitivity and `RESN`, strict validity inside a document |

## Contract requests

1. **AGENTS.md "no I/O" and GEDZIP.** The lane brief asked for "path-traversal-safe extraction".
   The engine meets it without filesystem writes, keeping the library pure: entries are
   validated and streamed by `iter_gedzip`. If the worker ever extracts to local disk, it must
   write only names that `validate_entry_name` accepts, under a fresh directory.
2. **Date wiring (DOM lane).** `model_parts.Date.value` is the raw 7.0 `DateValue` string, and
   `Date.phrase` holds the original text whenever an import had to interpret it. The domain date
   parser should accept exactly the 7.0 grammar and keep `phrase` alongside the parsed value, to
   match ARCHITECTURE's "the original text is kept".
3. **Privacy before export.** The engine does not decide who is living or what may leave a
   family space. The export path must apply PRIVACY.md (living people, sensitive facts, consent)
   before building the `GedcomDocument`. `mexico.apply_sensitivity(..., subject_living=True)`
   then adds `RESN CONFIDENTIAL` so other tools respect it.
4. **Sensitivity enumeration.** `_FH_SENSITIVITY` includes `GENETIC` because PRIVACY.md rule 2
   lists it as a class. Genetic data itself is permanently out of scope (rule 8). If the
   coordinator prefers to drop the value, it must be removed before any file is published,
   because the URIs and values are a public contract.
5. **Upload size.** The text readers do not cap input size; the API's import endpoint must bound
   the upload size before calling `import_gedcom551` or `parse_gedcom7`. GEDZIP reads have
   explicit `GedzipLimits`.
6. **HONEST_STATUS and README.** These need entries for GEDCOM 7.0 and 5.5.1 import and export,
   and for GEDZIP, once the API exposes them. This lane did not edit them, by ownership.
7. **Domain mapping.** When integrating `family_history.domain`:
   * `NameForm` parts map to `mexico.MexicanName`;
   * padrinos (`Association`) map to `Godparent`;
   * union kinds map to `EventKind`;
   * sensitivity classes map to `Sensitivity`.

   The engine's enum values are the GEDCOM payload values and should not be renamed.
