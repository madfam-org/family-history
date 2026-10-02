"""Declarative mapping between typed dataclasses and generic `Structure` trees.

A typed class declares, field by field, which substructure tag feeds it and what shape that
substructure has. Conversion is driven by those declarations, in both directions, so the
reader and both writers share one definition of the model.

Losslessness rules, applied per tag:

* A substructure is captured by a typed field only when its shape matches the declaration
  (for example, a text field only takes structures with a text payload and no substructures).
  If any structure with that tag does not fit, *every* structure with that tag stays in
  ``other``, so the relative order of same-tag structures never changes.
* A second occurrence of a singular field goes to ``other`` as well.
* Unknown standard tags and every extension tag (``_TAG``) go to ``other`` untouched.

Writing emits typed fields in declaration order and then ``other`` in its original order. The
specification lets substructures of different types be reordered, so this is a faithful round
trip, and it is deterministic.
"""

from __future__ import annotations

from dataclasses import Field, dataclass, field, fields
from enum import Enum
from typing import Any, Self, cast

from family_history.gedcom.structure import Structure


class Kind(Enum):
    TEXT = "text"
    TEXTS = "texts"
    POINTER = "pointer"
    POINTERS = "pointers"
    NODE = "node"
    NODES = "nodes"
    RAW = "raw"
    RAWS = "raws"
    PAYLOAD_TEXT = "payload_text"
    PAYLOAD_POINTER = "payload_pointer"
    TAG = "tag"
    XREF = "xref"


_SINGULAR = {Kind.TEXT, Kind.POINTER, Kind.NODE, Kind.RAW}
_OWN = {Kind.PAYLOAD_TEXT, Kind.PAYLOAD_POINTER, Kind.TAG, Kind.XREF}


@dataclass(frozen=True, slots=True)
class FieldSpec:
    kind: Kind
    tags: tuple[str, ...] = ()
    node: type[Typed] | None = None


def _spec(kind: Kind, tags: tuple[str, ...] = (), node: type[Typed] | None = None) -> Any:
    return {"gedcom": FieldSpec(kind, tags, node)}


def one_text(tag: str) -> Any:
    """A singular substructure whose text payload is stored as ``str | None``."""
    return field(default=None, metadata=_spec(Kind.TEXT, (tag,)))


def many_text(tag: str) -> Any:
    return field(default_factory=list, metadata=_spec(Kind.TEXTS, (tag,)))


def one_pointer(tag: str) -> Any:
    return field(default=None, metadata=_spec(Kind.POINTER, (tag,)))


def many_pointer(tag: str) -> Any:
    return field(default_factory=list, metadata=_spec(Kind.POINTERS, (tag,)))


def one_node(tag: str, node: type[Typed]) -> Any:
    return field(default=None, metadata=_spec(Kind.NODE, (tag,), node))


def many_node(tags: str | tuple[str, ...] | frozenset[str], node: type[Typed]) -> Any:
    """A list of typed substructures; several tags are allowed when ``node`` has a tag field."""
    names = (tags,) if isinstance(tags, str) else tuple(sorted(tags))
    return field(default_factory=list, metadata=_spec(Kind.NODES, names, node))


def one_raw(tag: str) -> Any:
    """A singular substructure kept as a generic `Structure`."""
    return field(default=None, metadata=_spec(Kind.RAW, (tag,)))


def many_raw(tags: str | tuple[str, ...] | frozenset[str]) -> Any:
    names = (tags,) if isinstance(tags, str) else tuple(sorted(tags))
    return field(default_factory=list, metadata=_spec(Kind.RAWS, names))


def payload_text() -> Any:
    """The structure's own text payload."""
    return field(default=None, metadata=_spec(Kind.PAYLOAD_TEXT))


def payload_pointer() -> Any:
    """The structure's own pointer payload (``@X@`` or ``@VOID@``)."""
    return field(default=None, metadata=_spec(Kind.PAYLOAD_POINTER))


def tag_name(default: str = "") -> Any:
    """The structure's own tag, for classes that model several tags (events, ordinances)."""
    return field(default=default, metadata=_spec(Kind.TAG))


def record_xref() -> Any:
    """The record's cross-reference identifier."""
    return field(default=None, metadata=_spec(Kind.XREF))


def _specs(cls: type[Any]) -> list[tuple[Field[Any], FieldSpec]]:
    cached: list[tuple[Field[Any], FieldSpec]] | None = cls.__dict__.get("_gedcom_specs")
    if cached is not None:
        return cached
    result = [(f, f.metadata["gedcom"]) for f in fields(cls) if "gedcom" in f.metadata]
    cls._gedcom_specs = result
    return result


def _own_payload_kind(cls: type[Typed]) -> Kind | None:
    for _, spec in _specs(cls):
        if spec.kind in (Kind.PAYLOAD_TEXT, Kind.PAYLOAD_POINTER):
            return spec.kind
    return None


def _node_class(spec: FieldSpec) -> type[Typed]:
    if spec.node is None:
        raise TypeError(f"field spec for {spec.tags} declares no node class")
    return spec.node


def _fits(spec: FieldSpec, item: Structure) -> bool:
    if item.xref is not None:
        return False
    if spec.kind in (Kind.TEXT, Kind.TEXTS):
        return item.payload is not None and item.pointer is None and not item.children
    if spec.kind in (Kind.POINTER, Kind.POINTERS):
        return item.pointer is not None and item.payload is None and not item.children
    if spec.kind in (Kind.NODE, Kind.NODES):
        own = _own_payload_kind(_node_class(spec))
        if own is Kind.PAYLOAD_TEXT:
            return item.pointer is None
        if own is Kind.PAYLOAD_POINTER:
            return item.payload is None
        return item.payload is None and item.pointer is None
    return True


class Typed:
    """Mixin for dataclasses that map to and from a `Structure`."""

    other: list[Structure]

    @classmethod
    def from_structure(cls, structure: Structure) -> Self:
        specs = _specs(cls)
        by_tag: dict[str, tuple[Field[Any], FieldSpec]] = {}
        values: dict[str, Any] = {}
        for f, spec in specs:
            for tag in spec.tags:
                by_tag[tag] = (f, spec)
            if spec.kind is Kind.PAYLOAD_TEXT:
                values[f.name] = structure.payload
            elif spec.kind is Kind.PAYLOAD_POINTER:
                values[f.name] = structure.pointer
            elif spec.kind is Kind.TAG:
                values[f.name] = structure.tag
            elif spec.kind is Kind.XREF:
                values[f.name] = structure.xref
            elif spec.kind not in _SINGULAR:
                values[f.name] = []
        unfit: set[str] = set()
        for child in structure.children:
            target = by_tag.get(child.tag)
            if target is not None and not _fits(target[1], child):
                unfit.add(child.tag)
        other: list[Structure] = []
        for child in structure.children:
            target = by_tag.get(child.tag)
            if target is None or child.tag in unfit:
                other.append(child)
                continue
            f, spec = target
            converted = _convert_in(spec, child)
            if spec.kind in _SINGULAR:
                if f.name in values:
                    other.append(child)
                else:
                    values[f.name] = converted
            else:
                values[f.name].append(converted)
        values["other"] = other
        return cls(**values)

    def to_structure(self, tag: str | None = None) -> Structure:
        specs = _specs(type(self))
        result = Structure(tag=tag or "")
        for f, spec in specs:
            value = getattr(self, f.name)
            if spec.kind in _OWN:
                _apply_own(result, spec.kind, value)
                continue
            items = value if spec.kind not in _SINGULAR else ([] if value is None else [value])
            for item in items:
                result.children.append(_convert_out(spec, item))
        if not result.tag:
            raise ValueError(f"{type(self).__name__} needs a tag to become a structure")
        result.children.extend(child.copy() for child in self.other)
        return result


def _apply_own(result: Structure, kind: Kind, value: Any) -> None:
    if kind is Kind.PAYLOAD_TEXT:
        result.payload = cast(str | None, value)
    elif kind is Kind.PAYLOAD_POINTER:
        result.pointer = cast(str | None, value)
    elif kind is Kind.XREF:
        result.xref = cast(str | None, value)
    elif kind is Kind.TAG and value:
        result.tag = cast(str, value)


def _convert_in(spec: FieldSpec, child: Structure) -> Any:
    if spec.kind in (Kind.TEXT, Kind.TEXTS):
        return child.payload
    if spec.kind in (Kind.POINTER, Kind.POINTERS):
        return child.pointer
    if spec.kind in (Kind.NODE, Kind.NODES):
        return _node_class(spec).from_structure(child)
    return child


def _convert_out(spec: FieldSpec, item: Any) -> Structure:
    tag = spec.tags[0]
    if spec.kind in (Kind.TEXT, Kind.TEXTS):
        return Structure(tag=tag, payload=cast(str, item))
    if spec.kind in (Kind.POINTER, Kind.POINTERS):
        return Structure(tag=tag, pointer=cast(str, item))
    if spec.kind in (Kind.NODE, Kind.NODES):
        node = cast(Typed, item)
        return node.to_structure(tag if len(spec.tags) == 1 else None)
    return cast(Structure, item).copy()
