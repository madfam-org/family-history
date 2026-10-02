"""GEDZIP: round trip, determinism and hostile-archive defences."""

from __future__ import annotations

import io
import stat
import zipfile

import pytest
from gedcom_helpers import SEVEN_FIXTURE, dataset, fixture_bytes

from family_history.gedcom import (
    GedzipError,
    GedzipLimits,
    build_gedzip,
    iter_gedzip,
    parse_gedcom7,
    read_gedzip,
    write_gedzip,
)
from family_history.gedcom.gedzip import local_file_name, validate_entry_name

JPEG = b"\xff\xd8\xff\xe0synthetic-jpeg-bytes"


def _zip(entries: list[tuple[str, bytes]], *, method: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=method) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return buffer.getvalue()


GED = dataset("0 @M1@ OBJE\n1 FILE media/foto%201.jpg\n2 FORM image/jpeg").encode()


def test_build_and_read_round_trip() -> None:
    doc = parse_gedcom7(fixture_bytes(SEVEN_FIXTURE)).document
    built = build_gedzip(doc, {"media/boda-1958.jpg": JPEG})
    assert built.diagnostics == []
    contents = read_gedzip(built.data)
    assert contents.media == {"media/boda-1958.jpg": JPEG}
    assert contents.diagnostics == []
    assert parse_gedcom7(contents.gedcom, strict=True).document == doc
    names = zipfile.ZipFile(io.BytesIO(built.data)).namelist()
    assert names[0] == "gedcom.ged"


def test_archives_are_deterministic() -> None:
    media = {"b.jpg": JPEG, "a/c.png": b"png"}
    assert write_gedzip(GED, media) == write_gedzip(GED, dict(reversed(list(media.items()))))
    infos = zipfile.ZipFile(io.BytesIO(write_gedzip(GED, media))).infolist()
    assert [i.filename for i in infos] == ["gedcom.ged", "a/c.png", "b.jpg"]
    assert infos[1].compress_type == zipfile.ZIP_STORED
    assert infos[0].compress_type == zipfile.ZIP_DEFLATED


def test_percent_encoded_paths_map_to_plain_zip_names() -> None:
    assert local_file_name("media/foto%201.jpg") == "media/foto 1.jpg"
    assert local_file_name("https://example.invalid/x.jpg") is None
    assert local_file_name("file:///C:/x.jpg") is None
    assert local_file_name("../x.jpg") is None
    archive = write_gedzip(GED, {"media/foto 1.jpg": JPEG})
    assert read_gedzip(archive).diagnostics == []


def test_missing_and_unreferenced_media_are_reported() -> None:
    contents = read_gedzip(_zip([("gedcom.ged", GED), ("extra.bin", b"x")]))
    assert [d.code for d in contents.diagnostics] == [
        "gedzip-missing-media",
        "gedzip-unreferenced",
    ]
    doc = parse_gedcom7(GED).document
    built = build_gedzip(doc, lambda name: None)
    assert [d.code for d in built.diagnostics] == ["gedzip-missing-media"]


def test_local_file_named_gedcom_ged_is_renamed_in_a_copy() -> None:
    doc = parse_gedcom7(dataset("0 @M1@ OBJE\n1 FILE gedcom.ged\n2 FORM text/plain")).document
    built = build_gedzip(doc, {"gedcom.ged": b"old file"})
    contents = read_gedzip(built.data)
    assert contents.media == {"gedcom-media.ged": b"old file"}
    assert b"1 FILE gedcom-media.ged" in contents.gedcom
    assert doc.media[0].files[0].value == "gedcom.ged"
    assert [d.code for d in built.diagnostics] == ["gedzip-renamed"]


@pytest.mark.parametrize(
    "name",
    [
        "../evil.jpg",
        "media/../../evil.jpg",
        "/etc/passwd",
        "C:/Windows/evil.jpg",
        "C:evil.jpg",
        "media\\evil.jpg",
        "media//double.jpg",
        "./media/x.jpg",
        "media/\x00null.jpg",
        "",
    ],
)
def test_unsafe_names_are_rejected(name: str) -> None:
    assert validate_entry_name(name) is not None
    # zipfile itself truncates names at NUL, so that case can only be checked on write.
    if name and "\x00" not in name:
        with pytest.raises(GedzipError):
            read_gedzip(_zip([("gedcom.ged", GED), (name, b"x")]))
    if name:
        with pytest.raises(GedzipError):
            write_gedzip(GED, {name: b"x"})


def test_symlink_entries_are_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("gedcom.ged", GED)
        info = zipfile.ZipInfo("media/link.jpg")
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")
    with pytest.raises(GedzipError, match="symbolic link"):
        read_gedzip(buffer.getvalue())


def test_duplicate_and_case_colliding_entries_are_rejected() -> None:
    with pytest.raises(GedzipError, match="only by case"):
        read_gedzip(_zip([("gedcom.ged", GED), ("A.jpg", b"1"), ("a.jpg", b"2")]))
    with pytest.warns(UserWarning):
        duplicate = _zip([("gedcom.ged", GED), ("x.jpg", b"1"), ("x.jpg", b"2")])
    with pytest.raises(GedzipError, match="duplicate"):
        read_gedzip(duplicate)


def test_encrypted_entries_are_refused() -> None:
    data = bytearray(_zip([("gedcom.ged", GED)], method=zipfile.ZIP_STORED))
    # Set the "encrypted" general-purpose flag in the local and central headers.
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = data.find(signature)
        data[start + offset] |= 0x01
    with pytest.raises(GedzipError, match="encrypted"):
        read_gedzip(bytes(data))


def test_missing_gedcom_and_not_a_zip() -> None:
    with pytest.raises(GedzipError, match="no gedcom.ged"):
        read_gedzip(_zip([("other.ged", GED)]))
    with pytest.raises(GedzipError, match="not a zip"):
        read_gedzip(b"plain text, not an archive")
    with pytest.raises(GedzipError, match="cannot be named"):
        write_gedzip(GED, {"gedcom.ged": b"x"})


def test_zip_bomb_ratio_and_size_limits() -> None:
    bomb = _zip([("gedcom.ged", GED), ("bomb.bin", b"\x00" * 5_000_000)])
    with pytest.raises(GedzipError, match="expands more than"):
        read_gedzip(bomb)
    with pytest.raises(GedzipError, match="exceeds"):
        read_gedzip(bomb, limits=GedzipLimits(max_entry_bytes=100_000, max_ratio=10_000))
    with pytest.raises(GedzipError, match="beyond"):
        read_gedzip(bomb, limits=GedzipLimits(max_total_bytes=1_000_000, max_ratio=10_000))
    big_ged = _zip([("gedcom.ged", GED * 100)])
    with pytest.raises(GedzipError, match="exceeds"):
        read_gedzip(big_ged, limits=GedzipLimits(max_gedcom_bytes=1000, max_ratio=10_000))


def test_entry_count_and_name_length_limits() -> None:
    many = _zip([("gedcom.ged", GED)] + [(f"m/{i}.jpg", b"x") for i in range(30)])
    with pytest.raises(GedzipError, match="exceed the limit"):
        read_gedzip(many, limits=GedzipLimits(max_entries=10))
    long_name = _zip([("gedcom.ged", GED), ("m/" + "a" * 300 + ".jpg", b"x")])
    with pytest.raises(GedzipError, match="too long"):
        read_gedzip(long_name, limits=GedzipLimits(max_name_length=100))


def test_lying_headers_do_not_bypass_limits() -> None:
    # Claim a tiny uncompressed size in the central directory for a large entry.
    data = bytearray(_zip([("gedcom.ged", GED), ("big.bin", b"\x01" * 400_000)]))
    central = data.find(b"PK\x01\x02", data.find(b"PK\x01\x02") + 4)
    data[central + 24 : central + 28] = (10).to_bytes(4, "little")
    with pytest.raises(GedzipError):
        list(iter_gedzip(bytes(data)))
    # And limits apply to the bytes actually produced, not to what headers say.
    honest = _zip([("gedcom.ged", GED), ("big.bin", b"\x01" * 400_000)])
    with pytest.raises(GedzipError, match="exceeds"):
        list(iter_gedzip(honest, limits=GedzipLimits(max_entry_bytes=1000, max_ratio=10_000)))


def test_iteration_streams_gedcom_first_and_accepts_file_objects() -> None:
    archive = _zip([("z.jpg", JPEG), ("gedcom.ged", GED)])
    names = [name for name, _ in iter_gedzip(io.BytesIO(archive))]
    assert names == ["gedcom.ged", "z.jpg"]
