"""Read and write FamilySearch GEDZIP (``.gdz``) archives, defensively.

A GEDZIP is a zip archive holding ``gedcom.ged`` plus one entry per local ``FILE`` path. This
module works on bytes and file-like objects only; it never writes to the filesystem (callers
stream entries to object storage). Reading treats every archive as hostile:

* entry names are validated before anything is read: no absolute paths, drive letters,
  backslashes, ``.``/``..`` segments, empty segments, control characters, symlinks or
  duplicates (also case-insensitive duplicates, which collide on many filesystems);
* encrypted entries are refused;
* sizes are measured while decompressing, never trusted from headers, against explicit
  limits: entry count, bytes per entry, total bytes and compression ratio (zip-bomb defence).
"""

from __future__ import annotations

import copy
import io
import re
import stat
import zipfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import BinaryIO
from urllib.parse import unquote

from family_history.gedcom.diagnostics import Diagnostic, Diagnostics, GedcomError
from family_history.gedcom.model import GedcomDocument
from family_history.gedcom.write7 import write_gedcom7

GEDCOM_ENTRY = "gedcom.ged"
_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
_CHUNK = 64 * 1024
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


class GedzipError(GedcomError):
    """The archive is unsafe, malformed or over a limit. Nothing from it should be used."""


@dataclass(frozen=True, slots=True)
class GedzipLimits:
    """Explicit resource limits for reading an archive. Defaults suit a family archive."""

    max_entries: int = 20_000
    max_entry_bytes: int = 1024 * 1024 * 1024
    max_total_bytes: int = 8 * 1024 * 1024 * 1024
    max_gedcom_bytes: int = 512 * 1024 * 1024
    max_ratio: int = 200
    max_name_length: int = 1024


@dataclass(slots=True)
class GedzipContents:
    gedcom: bytes
    media: dict[str, bytes] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def validate_entry_name(name: str, max_length: int = 1024) -> str | None:
    """Why ``name`` is unsafe as an archive path, or ``None`` when it is acceptable."""
    if not name:
        return "empty name"
    if len(name) > max_length:
        return "name too long"
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
        return "control character in name"
    if "\\" in name:
        return "backslash in name"
    if name.startswith("/"):
        return "absolute path"
    if _DRIVE_RE.match(name):
        return "drive letter"
    segments = name.rstrip("/").split("/")
    if any(segment in ("", ".", "..") for segment in segments):
        return "empty, '.' or '..' path segment"
    return None


def _check_info(info: zipfile.ZipInfo, limits: GedzipLimits) -> None:
    problem = validate_entry_name(info.filename, limits.max_name_length)
    if problem is not None:
        raise GedzipError(f"unsafe entry {info.filename!r}: {problem}")
    if info.flag_bits & 0x1:
        raise GedzipError(f"entry {info.filename!r} is encrypted; decrypt the archive first")
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise GedzipError(f"entry {info.filename!r} is a symbolic link")


def _entries(archive: zipfile.ZipFile, limits: GedzipLimits) -> list[zipfile.ZipInfo]:
    infos = archive.infolist()
    if len(infos) > limits.max_entries:
        raise GedzipError(f"{len(infos)} entries exceed the limit of {limits.max_entries}")
    seen: set[str] = set()
    folded: set[str] = set()
    files: list[zipfile.ZipInfo] = []
    for info in infos:
        _check_info(info, limits)
        if info.filename in seen:
            raise GedzipError(f"duplicate entry {info.filename!r}")
        if info.filename.casefold() in folded:
            raise GedzipError(f"entry {info.filename!r} differs from another only by case")
        seen.add(info.filename)
        folded.add(info.filename.casefold())
        if not info.is_dir():
            files.append(info)
    return files


def _read_entry(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int, limits: GedzipLimits
) -> bytes:
    buffer = bytearray()
    allowed = limits.max_ratio * max(info.compress_size, 1) + _CHUNK
    with archive.open(info) as stream:
        while True:
            chunk = stream.read(_CHUNK)
            if not chunk:
                break
            buffer.extend(chunk)
            if len(buffer) > limit:
                raise GedzipError(f"entry {info.filename!r} exceeds {limit} bytes")
            if len(buffer) > allowed:
                raise GedzipError(
                    f"entry {info.filename!r} expands more than {limits.max_ratio}x"
                )
    return bytes(buffer)


def iter_gedzip(
    source: bytes | BinaryIO, *, limits: GedzipLimits | None = None
) -> Iterator[tuple[str, bytes]]:
    """Yield ``(name, data)`` for every file entry, ``gedcom.ged`` first, within ``limits``.

    Raises `GedzipError` as soon as the archive turns out to be unsafe or over a limit.
    """
    limits = limits or GedzipLimits()
    stream: BinaryIO = io.BytesIO(source) if isinstance(source, bytes) else source
    try:
        archive = zipfile.ZipFile(stream)
    except (zipfile.BadZipFile, OSError) as exc:
        raise GedzipError(f"not a zip archive: {exc}") from exc
    with archive:
        files = _entries(archive, limits)
        if not any(info.filename == GEDCOM_ENTRY for info in files):
            raise GedzipError("the archive has no gedcom.ged entry")
        files.sort(key=lambda info: info.filename != GEDCOM_ENTRY)
        total = 0
        for info in files:
            is_gedcom = info.filename == GEDCOM_ENTRY
            cap = limits.max_gedcom_bytes if is_gedcom else limits.max_entry_bytes
            try:
                data = _read_entry(archive, info, cap, limits)
            except (zipfile.BadZipFile, OSError, EOFError, ValueError) as exc:
                raise GedzipError(f"entry {info.filename!r} is corrupt: {exc}") from exc
            total += len(data)
            if total > limits.max_total_bytes:
                raise GedzipError(f"archive expands beyond {limits.max_total_bytes} bytes")
            yield info.filename, data


def read_gedzip(source: bytes | BinaryIO, *, limits: GedzipLimits | None = None) -> GedzipContents:
    """Read a whole archive into memory and cross-check media against the dataset's paths."""
    entries = iter_gedzip(source, limits=limits)
    _, gedcom = next(entries)
    contents = GedzipContents(gedcom=gedcom)
    for name, data in entries:
        contents.media[name] = data
    diagnostics = Diagnostics(strict=False)
    referenced = set(local_file_names_from_bytes(gedcom))
    for name in sorted(referenced - contents.media.keys()):
        diagnostics.warning("gedzip-missing-media", f"FILE {name!r} is not in the archive")
    for name in sorted(contents.media.keys() - referenced):
        diagnostics.info("gedzip-unreferenced", f"archive entry {name!r} is not referenced")
    contents.diagnostics = list(diagnostics)
    return contents


def local_file_name(file_path: str) -> str | None:
    """The zip entry name for a 7.0 ``FilePath`` payload, or ``None`` if it is not local."""
    if not file_path or _SCHEME_RE.match(file_path) or file_path.startswith("/"):
        return None
    if "?" in file_path or "#" in file_path:
        return None
    name = unquote(file_path)
    return name if validate_entry_name(name) is None else None


def local_file_names_from_bytes(gedcom: bytes) -> list[str]:
    """Local file names referenced by ``FILE`` lines of a 7.0 stream (a light scan)."""
    names: list[str] = []
    text = gedcom.decode("utf-8", errors="replace")
    for match in re.finditer(r"(?m)^[0-9]+ FILE (.+?)\r?$", text):
        name = local_file_name(match.group(1))
        if name is not None:
            names.append(name)
    return names


def write_gedzip(
    gedcom: bytes, media: Mapping[str, bytes], *, compress_media: bool = False
) -> bytes:
    """Build a deterministic archive: ``gedcom.ged`` first, media sorted by name.

    Timestamps and permissions are fixed so identical input gives identical bytes. Media is
    stored uncompressed by default (photos and audio are already compressed).
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        _add(archive, GEDCOM_ENTRY, gedcom, compress=True)
        for name in sorted(media):
            if name == GEDCOM_ENTRY:
                raise GedzipError("a media entry cannot be named gedcom.ged")
            problem = validate_entry_name(name)
            if problem is not None:
                raise GedzipError(f"unsafe media name {name!r}: {problem}")
            _add(archive, name, media[name], compress=compress_media)
    return buffer.getvalue()


def _add(archive: zipfile.ZipFile, name: str, data: bytes, *, compress: bool) -> None:
    info = zipfile.ZipInfo(name, date_time=_FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, data)


@dataclass(slots=True)
class GedzipBuild:
    data: bytes
    diagnostics: list[Diagnostic] = field(default_factory=list)


def build_gedzip(
    document: GedcomDocument, media: Mapping[str, bytes] | Callable[[str], bytes | None]
) -> GedzipBuild:
    """Write ``document`` as 7.0 and package every local file it references.

    ``media`` maps zip names to bytes, or is a loader called with each name. A local file named
    ``gedcom.ged`` is renamed (and the ``FILE`` payload in the written copy updated) as the
    specification requires; ``document`` itself is not modified.
    Missing media is reported, not fatal: the family still gets their data.
    """
    document = copy.deepcopy(document)
    diagnostics = Diagnostics(strict=False)
    load = media if callable(media) else media.get
    packaged: dict[str, bytes] = {}
    for record in document.media:
        for file in record.files:
            name = local_file_name(file.value or "")
            if name is None:
                continue
            target = name
            if name == GEDCOM_ENTRY:
                target = _unused_name(packaged, "gedcom-media.ged")
                file.value = target
                diagnostics.warning("gedzip-renamed", f"local file {name!r} renamed to {target!r}")
            if target in packaged:
                continue
            data = load(name)
            if data is None:
                diagnostics.warning("gedzip-missing-media", f"no bytes for FILE {name!r}")
                continue
            packaged[target] = data
    archive = write_gedzip(write_gedcom7(document), packaged)
    return GedzipBuild(archive, list(diagnostics))


def _unused_name(taken: Mapping[str, bytes], wanted: str) -> str:
    stem, _, suffix = wanted.rpartition(".")
    candidate, counter = wanted, 2
    while candidate in taken or candidate == GEDCOM_ENTRY:
        candidate = f"{stem}-{counter}.{suffix}"
        counter += 1
    return candidate
