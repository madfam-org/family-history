"""The interchange formats without a database: native JSON, GEDCOM mappings and fixpoints."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest
from pydantic import ValidationError

from family_history.gedcom import write_gedzip
from family_history.gedcom.parse7 import parse_gedcom7
from family_history.interchange import native
from family_history.interchange.gedcom_in import GedcomImportError, tree_from_gedcom
from family_history.interchange.gedcom_map import (
    name_type_from_gedcom,
    name_type_to_gedcom,
    pedigree_from_gedcom,
    role_from_gedcom,
    split_particle,
)
from family_history.interchange.gedcom_out import export_gedcom7, export_gedcom551
from family_history.interchange.persist import OrderedIds
from family_history.interchange.synth import synthetic_tree
from family_history.worker.__main__ import healthcheck

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "gedcom"


@pytest.mark.parametrize(("seed", "generations"), [(0, 3), (1, 4), (2, 5), (3, 6), (17, 4)])
def test_gedcom7_export_is_valid_and_a_fixpoint(seed: int, generations: int) -> None:
    tree = synthetic_tree(seed, generations)
    first = export_gedcom7(tree)
    parse_gedcom7(first.data, strict=True)
    again, report = tree_from_gedcom(first.data)
    assert report.source_version == "7.0"
    assert export_gedcom7(again).data == first.data


@pytest.mark.parametrize("seed", [4, 5, 6])
def test_native_export_is_deterministic_whatever_the_load_order(seed: int) -> None:
    tree = synthetic_tree(seed, 4)
    first = native.export_bytes(tree)
    shuffled = synthetic_tree(seed, 4)
    rng = random.Random(seed)  # noqa: S311 - shuffles test input, not security
    for group in (shuffled.people, shuffled.events, shuffled.places, shuffled.citations):
        rng.shuffle(group)
    assert native.export_bytes(shuffled) == first
    assert native.export_bytes(native.to_tree(native.parse(first))) == first
    document = json.loads(first)
    assert document["format"] == "family-history-tree/v1"
    assert [p["id"] for p in document["people"]][:3] == ["P1", "P2", "P3"]


def _document(**changes: object) -> bytes:
    base = json.loads(native.export_bytes(synthetic_tree(8, 3)))
    base.update(changes)
    return json.dumps(base).encode()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["people"].append(dict(d["people"][0])),  # duplicate id
        lambda d: d["events"][0]["participants"].append({"person": "P999", "role": "principal"}),
        lambda d: d["places"][0].update(parent=d["places"][0]["id"]),  # a cycle
        lambda d: d["assertions"][0]["subject"].update(type="person"),
        lambda d: d["unions"][0].update(partners=[d["unions"][0]["partners"][0]] * 2),
        lambda d: d["events"][0]["associations"].append(
            {"person": "P1", "role": "other", "phrase": None}
        ),
        lambda d: d.update(extra=True),
        lambda d: d.update(format="family-history-tree/v2"),
    ],
)
def test_native_validation_rejects_broken_documents(mutate: object) -> None:
    document = json.loads(_document())
    mutate(document)  # type: ignore[operator]
    with pytest.raises(ValidationError):
        native.parse(json.dumps(document).encode())


def test_native_schema_is_draft_2020_12() -> None:
    schema = native.json_schema()
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["title"] == "family-history-tree/v1"
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "fixture",
    ["ancestry-like-551.ged", "gramps-like-551-ansel.ged", "myheritage-like-551.ged",
     "rootsmagic-like-551.ged", "familia-sintetica-7.ged"],  # fmt: skip
)
def test_vendor_files_become_trees(fixture: str) -> None:
    tree, report = tree_from_gedcom((FIXTURES / fixture).read_bytes())
    assert tree.people and tree.events
    assert report.source_version
    assert all(d["line"] is None or d["line"] > 0 for d in report.diagnostics)
    assert report.as_dict({})["record_counts"].get("INDI", 0) == len(tree.people)
    # Whatever came in exports as valid GEDCOM 7, and that export is a fixpoint.
    exported = export_gedcom7(tree)
    parse_gedcom7(exported.data, strict=True)
    assert export_gedcom7(tree_from_gedcom(exported.data)[0]).data == exported.data


def test_seven_fixture_keeps_mexican_details() -> None:
    tree, report = tree_from_gedcom((FIXTURES / "familia-sintetica-7.ged").read_bytes())
    assert report.extension_tags  # _FH_* and vendor tags are counted
    first = tree.people[0]
    assert first.names[0].apellido_paterno and first.names[0].apellido_materno
    kinds = {e.type for e in tree.events}
    assert "bracero_contract" in kinds and "baptism" in kinds
    baptism = next(e for e in tree.events if e.type == "baptism")
    assert baptism.sensitivity == "religion"
    assert baptism.associations and baptism.associations[0].role == "godparent"
    bracero = next(e for e in tree.events if e.type == "bracero_contract")
    assert bracero.date_value == "BET 1954 AND 1956"
    assert bracero.date_original and bracero.date_original.startswith("entre 1954 y 1956")
    assert any(a.field == "cause_of_death" and a.sensitivity == "health" for a in tree.assertions)


def test_gedzip_media_is_skipped_with_a_warning() -> None:
    gedcom = export_gedcom7(synthetic_tree(2, 3)).data
    archive = write_gedzip(gedcom, {"fotos/abuela.jpg": b"\xff\xd8synthetic"})
    tree, report = tree_from_gedcom(archive)
    assert report.container == "gedzip"
    assert [w["code"] for w in report.warnings].count("gedzip_media_skipped") == 1
    assert tree.people


@pytest.mark.parametrize(
    ("data", "code"),
    [(b"PK\x03\x04broken", "gedcom_invalid"), (b"hola", "gedcom_invalid")],
)
def test_unreadable_uploads(data: bytes, code: str) -> None:
    with pytest.raises(GedcomImportError) as caught:
        tree_from_gedcom(data)
    assert caught.value.code == code


def test_gedcom551_export_reimports() -> None:
    tree = synthetic_tree(9, 4)
    legacy = export_gedcom551(tree)
    assert b"2 VERS 5.5.1" in legacy.data
    again, report = tree_from_gedcom(legacy.data)
    assert report.source_version.startswith("5.5")
    assert len(again.people) == len(tree.people)


def test_mapping_tables_round_trip() -> None:
    assert split_particle("de la Garza") == ("de la", "Garza")
    assert split_particle("Del Valle") == ("Del", "Valle")
    assert split_particle("Garza") == (None, "Garza")
    assert split_particle("de") == (None, "de")
    for name_type in ("birth", "married", "aka", "immigrant", "baptismal", "religious", "other"):
        assert name_type_from_gedcom(*name_type_to_gedcom(name_type)) == name_type
    assert pedigree_from_gedcom("OTHER", "Hijastro o hijastra") == ("step", None)
    assert pedigree_from_gedcom("SEALING", None) == ("birth", "pedigree_sealing")
    assert pedigree_from_gedcom("OTHER", "tutor") == ("foster", "pedigree_other")
    assert role_from_gedcom("GODP", "Padrino") == ("association", "godparent", "Padrino")
    assert role_from_gedcom("FATH", None) == ("participant", "parent", None)
    assert role_from_gedcom("FRIEND", None) == ("association", "other", "Friend")


def test_private_and_living_people_are_marked() -> None:
    tree = synthetic_tree(3, 3)
    tree.people[0].visibility = "private"
    tree.people[1].living_status = "deceased"
    text = export_gedcom7(tree).data.decode("utf-8")
    assert "1 RESN CONFIDENTIAL, PRIVACY" in text
    again, _ = tree_from_gedcom(text.encode())
    assert sum(p.visibility == "private" for p in again.people) == 1


def test_ordered_ids_sort_in_issue_order() -> None:
    ids = OrderedIds()
    issued = [ids() for _ in range(50)]
    assert issued == sorted(issued)
    assert sorted(str(i) for i in issued) == [str(i) for i in issued]
    assert all(i.version == 4 for i in issued)


def test_worker_healthcheck(tmp_path: Path) -> None:
    beat = tmp_path / "heartbeat"
    assert healthcheck(str(beat)) == 1
    beat.touch()
    assert healthcheck(str(beat)) == 0
