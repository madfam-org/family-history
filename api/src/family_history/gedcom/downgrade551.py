"""Downgrade 7.0 structure trees to GEDCOM 5.5.1, marking what 5.5.1 cannot say.

The rule is *lossy but marked*: nothing is silently dropped. A 7.0 structure with no 5.5.1
equivalent is renamed to an underscore tag (``PHRASE`` -> ``_PHRASE``, ``EXID`` -> ``_EXID``,
``UID`` -> ``_UID``...), which legacy tools keep or ignore but never misread as standard data.
Each conversion is recorded in the export report. docs/GEDCOM.md lists every rule.
"""

from __future__ import annotations

from urllib.parse import unquote

from family_history.gedcom.diagnostics import Diagnostics
from family_history.gedcom.structure import VOID, Structure
from family_history.gedcom.upgrade551_tables import EXID_TYPES, LANGUAGES, MEDIA_TYPES

#: 7.0 tags that do not exist in 5.5.1 in any context.
SEVEN_ONLY = frozenset({"PHRASE", "UID", "NO", "CROP", "SDATE", "TRAN", "MIME", "INIL", "CREA"})
_LANG_NAMES: dict[str, str] = {}
for _name, _code in LANGUAGES.items():
    if _name.isascii():
        _LANG_NAMES.setdefault(_code, _name.title())
_EXTENSIONS: dict[str, str] = {"image/jpeg": "jpg", "image/tiff": "tif", "text/html": "htm"}
for _ext, _media in sorted(MEDIA_TYPES.items()):
    _EXTENSIONS.setdefault(_media, _ext.lower())
_CALENDARS = {"JULIAN": "@#DJULIAN@", "HEBREW": "@#DHEBREW@", "FRENCH_R": "@#DFRENCH R@"}
_ROLE_WORDS = {
    "GODP": "Godparent", "WITN": "Witness", "CLERGY": "Clergy", "FRIEND": "Friend",
    "NGHBR": "Neighbor", "OFFICIATOR": "Officiator", "PARENT": "Parent",
    "MULTIPLE": "Multiple birth sibling", "OTHER": "Other", "CHIL": "Child", "FATH": "Father",
    "MOTH": "Mother", "SPOU": "Spouse", "HUSB": "Husband", "WIFE": "Wife",
}
_ROLE_551 = frozenset({"CHIL", "HUSB", "WIFE", "MOTH", "FATH", "SPOU"})
_RANGE_WORDS = frozenset({"FROM", "TO", "BET", "AND", "BEF", "AFT", "ABT", "CAL", "EST"})


class Downgrader:
    def __init__(self, diagnostics: Diagnostics) -> None:
        self.d = diagnostics

    def run(self, roots: list[Structure]) -> list[Structure]:
        out: list[Structure] = []
        for root in roots:
            if root.tag == "HEAD":
                self._head(root, roots)
            elif root.tag == "SNOTE":
                root.tag = "NOTE"
            if not root.is_extension and root.tag != "TRLR":
                self._children(root, root)
            out.append(root)
        for root in out:
            if root.xref is not None and len(root.xref) > 22:
                self.d.warning(
                    "xref-length", f"{root.xref} is longer than 5.5.1's 22 characters", root.line
                )
        return out

    def _mark(self, node: Structure, reason: str) -> None:
        self.d.info("marked", f"{node.tag} -> _{node.tag}: {reason}", node.line)
        node.tag = "_" + node.tag

    def _head(self, head: Structure, roots: list[Structure]) -> None:
        schema = head.first("SCHMA")
        kept = [c for c in head.children if c.tag not in ("GEDC", "SCHMA")]
        gedc = Structure(tag="GEDC", children=[
            Structure(tag="VERS", payload="5.5.1"), Structure(tag="FORM", payload="LINEAGE-LINKED")
        ])
        if schema is not None and schema.children:
            listing = "\n".join(t.payload or "" for t in schema.all("TAG"))
            text = f"GEDCOM 7.0 extension tags used in this file:\n{listing}"
            note = next((c for c in kept if c.tag == "NOTE"), None)
            if note is None:
                kept.append(Structure(tag="NOTE", payload=text))
            else:
                note.payload = f"{note.payload or ''}\n{text}".lstrip("\n")
            self.d.info("schema", "HEAD.SCHMA written as a HEAD.NOTE listing the URIs")
        if not any(c.tag == "SOUR" for c in kept):
            kept.insert(0, Structure(tag="SOUR", payload="FAMILY_HISTORY"))
        if not any(c.tag == "SUBM" for c in kept):
            submitter = next((r for r in roots if r.tag == "SUBM" and r.xref), None)
            if submitter is None:
                submitter = Structure(tag="SUBM", xref="@FHSUBM@", children=[
                    Structure(tag="NAME", payload="family-history export")
                ])
                roots.insert(len(roots) - 1, submitter)
                self.d.info("submitter", "5.5.1 requires HEAD.SUBM; a submitter was added")
            kept.append(Structure(tag="SUBM", pointer=submitter.xref))
        kept.extend([gedc, Structure(tag="CHAR", payload="UTF-8")])
        head.children = kept

    def _children(self, node: Structure, record: Structure) -> None:
        index = 0
        while index < len(node.children):
            child = node.children[index]
            if child.pointer == VOID:
                child.pointer = None
                self._mark(child, "5.5.1 has no @VOID@ pointer")
            if child.is_extension:
                index += 1
                continue
            if self._fix(child, node, record):
                del node.children[index]
                continue
            if not child.is_extension:
                self._children(child, record)
            index += 1

    def _fix(self, node: Structure, parent: Structure, record: Structure) -> bool:
        """Rewrite ``node`` in place; return True when it moved elsewhere."""
        tag = node.tag
        if tag == "SNOTE":
            node.tag = "NOTE"
        elif tag == "DATE":
            self._date(node, parent)
        elif tag == "EXID":
            self._exid(node)
        elif tag in SEVEN_ONLY:
            self._mark(node, "no 5.5.1 equivalent")
        elif tag == "LANG" and parent.tag not in ("HEAD", "SUBM"):
            self._mark(node, "5.5.1 only has LANG in HEAD and SUBM")
        elif tag == "LANG":
            self._language(node)
        elif tag == "TITL" and parent.tag == "OBJE" and parent.pointer is not None:
            self._mark(node, "5.5.1 multimedia links carry no title")
        elif tag == "SEX" and node.payload == "X":
            node.payload = "U"
            node.children.append(Structure(tag="_SEX", payload="X"))
            self.d.warning("sex-x", "SEX X written as U with _SEX X", node.line)
        elif tag in ("PEDI", "RESN") or (
            (tag in ("STAT", "ADOP") and parent.tag == "FAMC")
            or (tag == "TYPE" and parent.tag == "NAME")
        ):
            self._enum(node)
        elif tag == "ROLE":
            self._role(node)
        elif tag == "ASSO":
            return self._association(node, parent, record)
        elif tag == "FILE":
            self._file(node)
        return False

    def _date(self, node: Structure, parent: Structure) -> None:
        value = node.payload or ""
        phrase = node.first("PHRASE")
        parts = []
        for part in value.split(" ") if value else []:
            if part in _CALENDARS:
                parts.append(_CALENDARS[part])
            elif part == "GREGORIAN":
                continue
            elif part == "BCE":
                parts.append("B.C.")
            elif part.startswith("_"):
                phrase_text = (phrase.payload if phrase else None) or value
                node.payload = f"({phrase_text})"
                self.d.warning("date-calendar", f"extension calendar date {value!r} kept as "
                               "a date phrase", node.line)
                node.children = [c for c in node.children if c is not phrase]
                return
            else:
                parts.append(part)
        converted = " ".join(parts)
        if phrase is not None and phrase.payload:
            if not converted:
                node.payload = f"({phrase.payload})"
                node.children.remove(phrase)
            elif not _RANGE_WORDS & set(parts):
                node.payload = f"INT {converted} ({phrase.payload})"
                node.children.remove(phrase)
            else:
                node.payload = converted
        else:
            node.payload = converted or None
        time = node.first("TIME")
        if time is not None and parent.tag not in ("CHAN", "HEAD"):
            self._mark(time, "5.5.1 has TIME only on change and header dates")

    def _exid(self, node: Structure) -> None:
        type_node = node.first("TYPE")
        uri = type_node.payload or "" if type_node is not None else ""
        base, _, fragment = uri.partition("#")
        for tag, registered in EXID_TYPES.items():
            if base == registered and type_node is not None:
                node.tag = tag
                node.children.remove(type_node)
                if tag == "RFN" and fragment:
                    node.payload = f"{unquote(fragment)}:{node.payload or ''}"
                return
        self._mark(node, "5.5.1 has no external identifiers")

    def _language(self, node: Structure) -> None:
        code = (node.payload or "").split("-")[0].lower()
        name = _LANG_NAMES.get(code)
        if name is None:
            self._mark(node, "language has no 5.5.1 name")
        else:
            node.payload = name

    def _enum(self, node: Structure) -> None:
        value = node.payload or ""
        phrase = node.first("PHRASE")
        if node.tag == "RESN" and "," in value:
            first = value.split(",")[0].strip()
            node.children.append(Structure(tag="_RESN", payload=value))
            self.d.warning("resn-list", f"RESN {value!r} reduced to {first!r}", node.line)
            value = first
        if node.tag == "TYPE" and value in ("OTHER", "PROFESSIONAL"):
            node.payload = (phrase.payload if phrase else None) or value.lower()
            if phrase is not None:
                node.children.remove(phrase)
            return
        if value == "OTHER":
            node.payload = (phrase.payload if phrase else None) or "other"
            if phrase is not None:
                node.children.remove(phrase)
            self.d.warning("enum-other", f"{node.tag} OTHER written as free text", node.line)
            return
        if node.tag != "QUAY":
            node.payload = value.lower()

    def _role(self, node: Structure) -> None:
        value = node.payload or ""
        phrase = node.first("PHRASE")
        if value in _ROLE_551 and phrase is None:
            return
        label = (phrase.payload if phrase else None) or _ROLE_WORDS.get(value, value)
        node.payload = f"({label})"
        if phrase is not None:
            node.children.remove(phrase)

    def _association(self, node: Structure, parent: Structure, record: Structure) -> bool:
        role = node.first("ROLE")
        if role is not None:
            phrase = role.first("PHRASE")
            label = (phrase.payload if phrase else None) or _ROLE_WORDS.get(
                role.payload or "", role.payload or ""
            )
            role.tag, role.payload = "RELA", label
            role.children = [c for c in role.children if c is not phrase]
        if parent.tag == "INDI":
            return False
        if record.tag == "INDI" and parent in record.children:
            # Godparents and witnesses of an individual's event: 5.5.1 only has INDI.ASSO, so
            # the association moves up and its RELA names the event it belonged to.
            rela = node.first("RELA")
            if rela is not None:
                when = parent.text("DATE")
                rela.payload = f"{rela.payload} ({parent.tag}{' ' + when if when else ''})"
            record.children.append(node)
            self.d.info(
                "asso-lifted", f"ASSO under {parent.tag} moved to the INDI record", node.line
            )
            return True
        self._mark(node, f"5.5.1 has no ASSO under {parent.tag}")
        return False

    def _file(self, node: Structure) -> None:
        url = node.payload or ""
        if url.startswith("file://"):
            path = unquote(url[len("file://") :])
            node.payload = path[1:] if len(path) > 2 and path[0] == "/" and path[2] == ":" else path
        elif "://" not in url:
            node.payload = unquote(url)
        form = node.first("FORM")
        if form is not None:
            media = (form.payload or "").split(";")[0].strip().lower()
            ext = _EXTENSIONS.get(media)
            if ext is None:
                suffix = (node.payload or "").rsplit(".", 1)
                ext = suffix[1].lower() if len(suffix) == 2 and "/" not in suffix[1] else media
            form.payload = ext
            for medium in form.all("MEDI"):
                medium.tag = "TYPE"
                self._enum(medium)
