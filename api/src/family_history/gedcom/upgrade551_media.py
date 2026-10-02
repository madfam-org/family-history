"""5.5.1 -> 7.0 helpers for multimedia records and file paths."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from family_history.gedcom.diagnostics import Diagnostics
from family_history.gedcom.structure import Structure
from family_history.gedcom.upgrade551_tables import MEDIA_TYPES, MEDIUM_WORDS, UNKNOWN_MEDIA_TYPE

_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_PERCENT_OK_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_UNSAFE = set(' "<>\\^`{|}')


def _escape_url(path: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(path):
        char = path[index]
        if char == "%" and _PERCENT_OK_RE.match(path, index):
            out.append(path[index : index + 3])
            index += 3
            continue
        if char == "%" or char in _UNSAFE or ord(char) < 0x20:
            out.append("".join(f"%{byte:02X}" for byte in char.encode("utf-8")))
        else:
            out.append(char)
        index += 1
    return "".join(out)


def to_file_url(path: str) -> str:
    """Turn a 5.5.1 file reference into a 7.0 ``FilePath`` (a URL string).

    * ``C:\\fotos\\boda.jpg`` -> ``file:///C:/fotos/boda.jpg`` (a non-local file);
    * ``\\\\server\\share\\x.jpg`` -> ``file://server/share/x.jpg``;
    * ``/home/x.jpg`` -> ``file:///home/x.jpg``;
    * ``fotos\\boda 1.jpg`` -> ``fotos/boda%201.jpg`` (a local file, GEDZIP-ready);
    * URLs with a scheme keep it; unsafe characters are percent-encoded everywhere.
    """
    text = path.strip()
    if text.startswith("\\\\"):
        return "file://" + _escape_url(text[2:].replace("\\", "/"))
    if _DRIVE_RE.match(text):
        return "file:///" + _escape_url(text.replace("\\", "/"))
    if _SCHEME_RE.match(text) and not _DRIVE_RE.match(text):
        return _escape_url(text)
    text = text.replace("\\", "/")
    if text.startswith("/"):
        return "file://" + _escape_url(text)
    return _escape_url(text)


def media_type_for(form: str | None, path: str | None) -> tuple[str, bool]:
    """Map a 5.5.1 FORM (or the file extension) to a media type; flag unknown ones."""
    if form and "/" in form:
        return form.strip(), True
    key = (form or "").strip().lstrip(".").upper()
    if not key and path:
        key = PurePosixPath(path.replace("\\", "/")).suffix.lstrip(".").upper()
    if key in MEDIA_TYPES:
        return MEDIA_TYPES[key], True
    return UNKNOWN_MEDIA_TYPE, False


def medium_value(node: Structure, diagnostics: Diagnostics) -> None:
    """Upper-case a ``MEDI`` value, or turn an unknown one into ``OTHER`` + ``PHRASE``."""
    original = (node.payload or "").strip()
    mapped = MEDIUM_WORDS.get(original.lower())
    if mapped is not None:
        node.payload = mapped
        return
    if original.upper() in MEDIUM_WORDS.values() or original.upper() == "OTHER":
        node.payload = original.upper()
        return
    node.payload = "OTHER"
    if original:
        node.children.insert(0, Structure(tag="PHRASE", payload=original, line=node.line))
        diagnostics.warning(
            "medium-other", f"medium {original!r} kept as OTHER + PHRASE", node.line
        )


def upgrade_media_record(record: Structure, diagnostics: Diagnostics) -> None:
    """Reshape a 5.5 / 5.5.1 ``OBJE`` record into the 7.0 ``FILE``/``FORM``/``MEDI`` shape."""
    top_form = record.first("FORM")
    top_title = record.first("TITL")
    for blob in record.all("BLOB"):
        diagnostics.warning(
            "blob-dropped", "embedded BLOB media data has no 7.0 equivalent; dropped", blob.line
        )
    record.children = [
        c for c in record.children if c.tag not in ("BLOB", "FORM") and c is not top_title
    ]
    files = record.all("FILE")
    if not files:
        diagnostics.warning("media-without-file", "OBJE has no FILE", record.line)
    for index, file in enumerate(files):
        if top_form is not None and file.first("FORM") is None:
            file.children.insert(0, top_form.copy())
        if top_title is not None and index == 0 and file.first("TITL") is None:
            file.children.append(top_title.copy())
        _upgrade_file(file, diagnostics)
    if top_title is not None and not files:
        record.children.append(top_title)


def _upgrade_file(file: Structure, diagnostics: Diagnostics) -> None:
    original = file.payload or ""
    if original:
        url = to_file_url(original)
        if url != original:
            diagnostics.info(
                "file-path", f"file path {original!r} written as URL {url!r}", file.line
            )
        file.payload = url
    form = file.first("FORM")
    if form is None:
        form = Structure(tag="FORM", line=file.line)
        file.children.insert(0, form)
    media_type, known = media_type_for(form.payload, original)
    if not known:
        diagnostics.warning(
            "media-type-unknown",
            f"unknown media FORM {form.payload!r}; written as {media_type}",
            form.line,
        )
    form.payload = media_type
    for child in form.children:
        if child.tag == "TYPE":
            child.tag = "MEDI"
        if child.tag == "MEDI":
            medium_value(child, diagnostics)
