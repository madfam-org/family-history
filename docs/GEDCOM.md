# GEDCOM support

> Last Updated: 2026-10-01

Interop is a promise to families: they can leave with everything. This document describes what
the GEDCOM engine (`family_history.gedcom`, in `api/src/family_history/gedcom/`) reads and
writes, the extension tags it defines, what is lost when exporting to older formats, and the
limits it enforces.

The engine is pure Python standard library. It works on bytes and never touches the network
or the filesystem.

## Support matrix

| Capability | Status | Notes |
|---|---|---|
| Read FamilySearch GEDCOM 7.0 (7.0.0 – 7.0.18) | Supported | Strict mode raises with every violation and its line number. Tolerant mode repairs and reports warnings |
| Validate against the 7.0 grammar | Supported | Every record, substructure, cardinality, payload type and enumeration in 7.0.18, plus pointer targets and `SCHMA` |
| Read GEDCOM 5.5.1 and 5.5 | Supported (tolerant only) | Upgraded to the 7.0 model, with an import report |
| Read GEDCOM 5.5.5 | Supported through the 5.5.1 reader | 5.5.5 is a stricter 5.5.1 profile |
| Write GEDCOM 7.0 | Supported | Deterministic; UTF-8 with byte-order mark; LF by default |
| Write GEDCOM 5.5.1 | Supported | For legacy desktop tools; constructs 5.5.1 lacks are marked, never dropped |
| Read and write GEDZIP (`.gdz`) | Supported | Hostile-archive defences, see [Limits](#limits) |
| Encrypted GEDZIP | Not supported | Refused with a clear error; decrypt first |
| Character sets | UTF-8 (with or without BOM), UTF-16 with BOM; 5.5.1 `CHAR` `UTF-8`, `UNICODE`, `ASCII`, `ANSEL` (best effort) and the non-standard `ANSI`, `IBMPC`, `MACINTOSH` | Mislabelled files are detected and reported |
| Line endings | CR, LF and CR-LF, also mixed | |
| Unknown and extension structures | Preserved losslessly | Kept in place on round trip, including whole extension records |
| Semantic dates (calendar conversion, sorting) | Out of scope here | `DATE` payloads stay strings; only their syntax is checked. The domain layer interprets them |
| GEDCOM X | Not supported | |

### Round-trip guarantees

* Reading a 7.0 file and writing it back gives a document equal to the one read, and writing
  that again gives identical bytes.
* The writer emits `HEAD` first (`GEDC.VERS 7.0`, then `SCHMA`), then records grouped by type
  (SUBM, INDI, FAM, SOUR, REPO, OBJE, SNOTE, extension records) in document order. Inside a
  structure, substructures of the same type keep their order. The specification allows
  substructures of different types to be reordered, and the writer uses that to produce one
  canonical order.
* GEDCOM 7.0 has no line length limit, so the 7.0 writer never emits `CONC`. Multi-line text
  becomes `CONT` lines. Only a leading `@` is doubled.

## MADFAM extension tags

Every extension tag below is a *documented* extension. Whenever a dataset uses one, the 7.0
writer declares it in `HEAD.SCHMA` with the URI shown. The URI is the identifier; the tag is
only an abbreviation inside one file. These URIs are stable and will never be reassigned.

### `_FH_SURNAME_LINE`

* **URI:** `https://github.com/madfam-org/family-history/blob/main/docs/GEDCOM.md#_fh_surname_line`
* **Where:** under `NAME.SURN` (and `NAME.TRAN.SURN`).
* **Payload:** enumeration: `PATERNAL`, `MATERNAL` or `OTHER`.
* **Meaning:** which parent's line this surname comes from. Mexican names carry an apellido
  paterno and an apellido materno; GEDCOM 7.0 has `SURN` pieces but no way to say which is which.

### `_FH_SURNAME_ORDER`

* **URI:** `https://github.com/madfam-org/family-history/blob/main/docs/GEDCOM.md#_fh_surname_order`
* **Where:** under `NAME`.
* **Payload:** enumeration: `PATERNAL_FIRST` or `MATERNAL_FIRST`.
* **Meaning:** the order in which the surnames are displayed. It is the order of the `SURN`
  pieces and of the text between the slashes. Mexico writes paterno first; some binational
  families do not.

```gedcom
1 NAME María Guadalupe /Hernández López/
2 GIVN María Guadalupe
2 NICK Lupita
2 SURN Hernández
3 _FH_SURNAME_LINE PATERNAL
2 SURN López
3 _FH_SURNAME_LINE MATERNAL
2 _FH_SURNAME_ORDER PATERNAL_FIRST
```

### `_FH_SENSITIVITY`

* **URI:** `https://github.com/madfam-org/family-history/blob/main/docs/GEDCOM.md#_fh_sensitivity`
* **Where:** under any event, attribute, `NOTE` or `CAUS`.
* **Payload:** a list of enumerations, comma-separated: `RELIGION`, `HEALTH`, `GENETIC`,
  `ETHNICITY`, `SEXUAL`, `POLITICAL`.
* **Meaning:** the sensitive-data classes of [PRIVACY.md](./PRIVACY.md) rule 2 that the fact
  carries. Sacramental events default to `RELIGION`; cause of death defaults to `HEALTH`. When
  the subject is living, the structure (or, for `CAUS`, its event) also carries
  `RESN CONFIDENTIAL`, so tools that ignore the extension still treat it as confidential.

### `_FH_EVENT_KIND`

* **URI:** `https://github.com/madfam-org/family-history/blob/main/docs/GEDCOM.md#_fh_event_kind`
* **Where:** under `MARR` or `EVEN` (individual or family).
* **Payload:** enumeration: `CIVIL_MARRIAGE`, `RELIGIOUS_MARRIAGE`, `FREE_UNION`,
  `QUINCEANERA`, `BRACERO_CONTRACT` or `BORDER_CROSSING`.
* **Meaning:** the machine-readable kind of the event. The standard `TYPE` always carries the
  same information as human-readable text (in Spanish by default), so other tools lose nothing
  they could display.

## Mexican mappings

`family_history.gedcom.mexico` provides pure functions for these mappings. Standard GEDCOM
comes first; an extension is added only for what the standard cannot say.

| Concept | GEDCOM 7.0 |
|---|---|
| Nombre(s) de pila | `NAME.GIVN` |
| Apellido paterno and materno | Two `NAME.SURN` pieces in display order, each with `_FH_SURNAME_LINE`, plus `_FH_SURNAME_ORDER`. Without the extensions (files from other tools), the first two `SURN` pieces, or the two words between the slashes, are read as paterno and materno in display order |
| Apodos | `NAME.NICK`, one per apodo |
| Padrinos per sacrament | `ASSO @I…@` with `ROLE GODP` under the sacrament event (`BAPM`, `CONF`, `FCOM`, or `MARR` for a religious wedding), with a `PHRASE` such as «Padrino de bautismo» or «Padrinos de arras». Unknown padrinos use `@VOID@` with a `PHRASE`. Compadres are derived from these and never stored |
| Civil marriage | `MARR` + `TYPE Matrimonio civil` + `_FH_EVENT_KIND CIVIL_MARRIAGE` |
| Religious marriage | `MARR` + `TYPE Matrimonio religioso` + `_FH_EVENT_KIND RELIGIOUS_MARRIAGE` + `_FH_SENSITIVITY RELIGION` |
| Unión libre | `FAM.EVEN` + `TYPE Unión libre` + `_FH_EVENT_KIND FREE_UNION` |
| XV años | `INDI.EVEN` + `TYPE XV años` + `_FH_EVENT_KIND QUINCEANERA` (padrinos as above) |
| Bracero contract | `INDI.EVEN` + `TYPE Contrato bracero` + `_FH_EVENT_KIND BRACERO_CONTRACT` |
| Border crossing | `INDI.EVEN` + `TYPE Cruce fronterizo` + `_FH_EVENT_KIND BORDER_CROSSING` |
| Sensitivity class | `_FH_SENSITIVITY`, plus `RESN CONFIDENTIAL` for living people where `RESN` is permitted |

On import, kinds are recognized from `_FH_EVENT_KIND` first and otherwise from common `TYPE`
text in Spanish or English (for example «Religious», «Iglesia», «Quinceañera», «Programa
Bracero»).

## Importing GEDCOM 5.5.1

The importer never stops on bad input. It returns a 7.0-shaped document and an import report.
The report holds:

* record counts per 5.5.1 record type, and the records it had to create;
* every diagnostic, with its line number;
* the extension tags seen;
* the cross-reference ids it rewrote.

After upgrading, the result is validated against 7.0. Anything still invalid is kept as found
and reported as `residual-*`.

| 5.5.1 | 7.0 result | Report |
|---|---|---|
| `HEAD.GEDC.VERS 5.5.1`, `GEDC.FORM`, `CHAR`, `FILE` | `GEDC.VERS 7.0`; the others removed | info |
| `HEAD.SUBN`, `SUBN` records (LDS submissions) | Removed | warning |
| `LANG English`, `LANG Spanish`… | BCP 47 (`en`, `es`…); unknown names become `und` | warning when unknown |
| `0 @N1@ NOTE text`, `NOTE @N1@` | `SNOTE` record and `SNOTE` pointer | info |
| Cross-reference ids outside the 7.0 grammar (`@s-1@`) | Upper-cased, other characters become `_`, made unique; every pointer follows | warning |
| `CONC` / `CONT` | Joined | |
| `@@` anywhere in a value | `@` | |
| Date escapes `@#DJULIAN@`, `@#DHEBREW@`, `@#DFRENCH R@`, `@#DGREGORIAN@` | `JULIAN`, `HEBREW`, `FRENCH_R`; Gregorian is the default and is omitted | info |
| `@#DROMAN@`, `@#DUNKNOWN@` | Empty `DATE` + `PHRASE` with the original | warning |
| `B.C.` | `BCE` | info |
| Dual years `1750/51` | The new-style year (`1751`) + `PHRASE` with the original, as in appendix A of the 7.0 specification | warning |
| `INT 1850 (text)` | `DATE 1850` + `PHRASE text` | warning |
| `(text)` | Empty `DATE` + `PHRASE text` | warning |
| Vendor spellings (`Abt.`, `about`, `circa`, `bet. … and`, lower-case, full or Spanish month names, ISO `1850-03-12`, leading zeros) | Normalized to the 7.0 grammar | info |
| Anything else that is not a date | Empty `DATE` + `PHRASE` with the original | warning |
| `AGE CHILD`, `INFANT`, `STILLBORN` | `< 8y`, `< 1y`, `0y`, each with a `PHRASE` | info |
| `AGE 27` and spacing variants | `27y` | info |
| Unreadable ages | Empty `AGE` + `PHRASE` | warning |
| `SEX` other than M, F, U | `U` (Spanish and English words are mapped) | warning |
| Lower-case `PEDI`, `STAT`, `RESN`, `NAME.TYPE`, `MEDI`, `FAMC.ADOP` | Upper-cased 7.0 values | |
| Unknown `PEDI`, `NAME.TYPE` and `MEDI` values | `OTHER` + `PHRASE` with the original | warning |
| Unknown `STAT`, `RESN` and `FAMC.ADOP` values (these have no `OTHER`) | Kept as found | `residual-payload-syntax` warning |
| `ASSO` + `RELA text` | `ASSO` + `ROLE` (`GODP` for padrino/madrina/godfather, `WITN` for testigo/witness, and so on; otherwise `OTHER`) + `PHRASE` with the original. `ASSO.TYPE INDI` is removed | info |
| `ASSO` without `RELA` | `ROLE OTHER` | warning |
| Citation `EVEN.ROLE (Godmother)` | `ROLE GODP` + `PHRASE` | info |
| `AFN`, `RFN`, `RIN` | `EXID` with `TYPE https://gedcom.io/terms/v7/AFN`, `…/RFN#<resource>` or `…/RIN#<HEAD.SOUR>` (registered URIs) | info |
| `SOUR text` citation without a record | A new `SOUR` record (`TITL` from the text, `TEXT` from its `TEXT` lines) and a pointer to it | warning |
| `OBJE` link with an embedded `FILE` | A new `OBJE` record and a pointer to it; the link keeps its `TITL` | warning |
| `OBJE.FILE` paths | URLs: `C:\fotos\a.jpg` becomes `file:///C:/fotos/a.jpg`; `fotos\a b.jpg` becomes `fotos/a%20b.jpg` | info |
| `FORM jpg`, `FORM.TYPE photo`; 5.5 `OBJE.FORM` and `OBJE.TITL` | `FORM image/jpeg` + `MEDI PHOTO`, moved under each `FILE`; unknown forms become `application/octet-stream` | warning when unknown |
| `BLOB` | Removed: embedded binary media has no 7.0 form | warning |
| Event with text (`1 DEAT ahogado`) | `DEAT Y` + `NOTE` with the text | warning |
| `EVEN`, `FACT`, `IDNO` without `TYPE` | `TYPE` added (the `EVEN` text, or «Unspecified») | warning |
| `ALIA` with a name instead of a pointer | `NAME` with `TYPE AKA` | warning |
| `LATI 19.43`, `LONG -99.13` | `N19.43`, `W99.13` | info |
| Vendor extensions (`_APID`, `_UPD`, `_MARNM`, `_UID`, `_TMPLT`, `_MTTAG` records…) | Preserved exactly, subtree included | listed in the report |

### Character sets

| `HEAD.CHAR` | Read as |
|---|---|
| Byte-order mark present | The BOM's encoding wins; a disagreeing `CHAR` is reported |
| `UTF-8` | UTF-8 |
| `UNICODE` | UTF-16 when there is a BOM or NUL pattern; otherwise UTF-8, reported |
| `ANSEL` | ANSEL with combining marks reordered and NFC-normalized. Undefined bytes become U+FFFD and the report names each byte value and count. A file that says ANSEL but is valid UTF-8 is read as UTF-8, reported |
| `ASCII` | UTF-8 (a superset); non-ASCII content is reported |
| `ANSI`, `IBMPC`, `MACINTOSH` (not 5.5.1 values) | Windows-1252, code page 437, Mac Roman; reported |
| Missing or unknown | UTF-8, falling back to Windows-1252 at the first invalid byte; reported |

## Exporting GEDCOM 5.5.1

The 5.5.1 writer serves families moving to legacy desktop tools. Its output is UTF-8
(`CHAR UTF-8`) with CR-LF line endings and no byte-order mark by default. Lines are at most
255 characters: longer text is split with `CONC` at points that leave no leading or trailing
space, because many legacy readers trim them. Every `@` is doubled except in date escapes.

The rule is **lossy but marked**. A 7.0 structure that 5.5.1 cannot express is renamed to an
underscore tag, and its subtree is kept. Legacy tools then keep or ignore it, but never misread
it as standard data. Every conversion is listed in the export report.

| 7.0 | 5.5.1 output | What is lost |
|---|---|---|
| `HEAD.SCHMA` | Removed; a `HEAD.NOTE` lists every extension tag and its URI | Machine-readable tag definitions |
| `HEAD` without `SOUR` or `SUBM` | `SOUR FAMILY_HISTORY` and a submitter record are added, because 5.5.1 requires them | Nothing |
| `SNOTE` record / pointer | `NOTE` record / pointer | Nothing |
| `DATE` calendars, `BCE` | `@#DJULIAN@`, `@#DHEBREW@`, `@#DFRENCH R@`, `B.C.` | Nothing |
| `DATE` + `PHRASE` | `INT <date> (<phrase>)`; `(<phrase>)` when the date is empty; for ranges, the phrase stays as `_PHRASE` | Nothing; the range-plus-phrase case is marked |
| Extension calendars (`_MAYA …`) | `(<phrase or original>)` | The structured date |
| `TIME` under an event `DATE` | `_TIME` | Standard placement |
| `PHRASE` elsewhere, `UID`, `NO`, `CROP`, `SDATE`, `TRAN`, `MIME`, `INIL`, `CREA` | `_PHRASE`, `_UID`, `_NO`, `_CROP`, `_SDATE`, `_TRAN`, `_MIME`, `_INIL`, `_CREA` | Standard meaning for legacy tools |
| `LANG` outside `HEAD`/`SUBM` | `_LANG` | Standard meaning |
| `HEAD.LANG`, `SUBM.LANG` | 5.5.1 language names (`Spanish`); unknown codes become `_LANG` | Region subtags (`es-MX` becomes `Spanish`) |
| `EXID` with `AFN`/`RFN`/`RIN` types | `AFN`, `RFN resource:id`, `RIN` | Nothing |
| Other `EXID` | `_EXID` | Standard meaning |
| `SEX X` | `SEX U` + `_SEX X` | Standard value |
| `RESN` with several values | The first value, lower-case, plus `_RESN` with the full list | Standard meaning of the extra values |
| `PEDI`, `STAT`, `NAME.TYPE`, `MEDI` | Lower-case 5.5.1 values; `OTHER` + `PHRASE` becomes the phrase text | Enumerated meaning of `OTHER` |
| `ROLE` in citations | `CHIL`, `HUSB`, `WIFE`, `MOTH`, `FATH`, `SPOU` as-is; others become `(<phrase or English word>)` | Enumerated meaning |
| `ASSO` + `ROLE` | `ASSO` + `RELA <phrase or English word>` | Enumerated meaning |
| `ASSO` under an individual's event (padrinos) | Moved to the `INDI` record, with `RELA` naming the event and date (`Padrino de bautismo (BAPM 2 APR 1931)`) | Structural link to the event; it stays in the `RELA` text |
| `ASSO` under `FAM` or a family event | `_ASSO` | Standard meaning |
| `@VOID@` pointers | The structure becomes `_<TAG>` without a pointer; its subtree is kept as 7.0 | The placeholder's standard meaning |
| Multimedia link `TITL` | `_TITL` | Standard meaning |
| `FILE` URLs | Local paths percent-decoded (`media/a%20b.jpg` becomes `media/a b.jpg`); `file://` URLs become paths; web URLs stay | Nothing |
| `FORM image/jpeg` + `MEDI PHOTO` | `FORM jpg` + `TYPE photo` | Media-type parameters |
| MADFAM extension tags | Kept as they are | URIs (listed in the `HEAD.NOTE`) |
| Cross-reference ids longer than 22 characters | Kept; reported | 5.5.1 conformance |

Re-importing a 5.5.1 export with this engine restores the 7.0 structures, except those marked
with underscore tags, which stay as extensions.

## GEDZIP

* `build_gedzip(document, media)` writes the dataset as 7.0 and adds one entry per local `FILE`
  path. `media` is either a mapping from entry names to bytes or a loader. Paths are
  percent-decoded into zip entry names, as the specification requires. A local file named
  `gedcom.ged` is renamed in the written copy. Missing media is reported, not fatal.
* `write_gedzip(gedcom, media)` is deterministic: `gedcom.ged` comes first and media is sorted by
  name, with fixed timestamps and permissions. `gedcom.ged` is deflated and media is stored,
  because photos and audio are already compressed.
* `read_gedzip(...)` and `iter_gedzip(...)` treat every archive as hostile. They work in memory
  or on a stream and never write to disk.

## Limits

| Limit | Default | Where |
|---|---|---|
| GEDZIP entries | 20 000 | `GedzipLimits.max_entries` |
| GEDZIP bytes per media entry | 1 GiB | `GedzipLimits.max_entry_bytes` |
| GEDZIP `gedcom.ged` bytes | 512 MiB | `GedzipLimits.max_gedcom_bytes` |
| GEDZIP total uncompressed bytes | 8 GiB | `GedzipLimits.max_total_bytes` |
| GEDZIP compression ratio per entry | 200:1 | `GedzipLimits.max_ratio` |
| GEDZIP entry name length | 1024 characters | `GedzipLimits.max_name_length` |
| Structure nesting depth | 128 levels; deeper lines are clamped and reported | `max_depth` on every reader |
| 5.5.1 output line length | 255 characters | 5.5.1 writer |

GEDZIP sizes are measured while decompressing; header values are never trusted. An archive is
refused outright when any entry has one of these problems:

* an absolute path, a drive letter, a backslash, a `.` or `..` segment, an empty segment or a
  control character in its name;
* it is a symbolic link;
* it is encrypted;
* its name duplicates another entry's, including names that differ only by case.

The plain-text readers do not cap input size. Callers must bound the bytes they accept before
parsing.
