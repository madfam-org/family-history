"""Validate `Structure` trees against the FamilySearch GEDCOM 7.0.18 grammar.

Checks performed, each reported with the offending line:

* dataset shape: ``HEAD`` first with ``GEDC.VERS 7.x``, ``TRLR`` last, nothing after it;
* record tags, permitted substructures per context, cardinality (required and singular);
* payload presence and kind (none, ``Y``, pointer, text) and data-type syntax, including
  enumeration values and DATE syntax (dates stay strings; only their grammar is checked);
* pointers: every target exists and is a record of the expected type, xrefs are unique;
* ``SCHMA``: one URI per extension tag.

Extension structures (``_TAG``) and everything beneath them are skipped: their meaning is
defined by their own documentation, not by this specification.
"""

from __future__ import annotations

from collections import Counter

from family_history.gedcom.datatypes import EXT_TAG_RE, check_value
from family_history.gedcom.diagnostics import Diagnostics
from family_history.gedcom.spec import RECORD_TYPES, STRUCTURE_TYPES, StructureType
from family_history.gedcom.structure import VOID, Structure


def validate_structures(roots: list[Structure], diagnostics: Diagnostics) -> None:
    """Record every 7.0 violation found in ``roots`` (level-0 structures, as read)."""
    _check_shape(roots, diagnostics)
    targets = _collect_xrefs(roots, diagnostics)
    for root in roots:
        if root.tag in ("HEAD", "TRLR") or root.is_extension:
            if root.tag == "HEAD":
                _check_node(root, STRUCTURE_TYPES["g7:HEAD"], targets, diagnostics)
            continue
        uri = RECORD_TYPES.get(root.tag)
        if uri is None:
            diagnostics.error("unknown-record", f"{root.tag} is not a record type", root.line)
            continue
        _check_node(root, STRUCTURE_TYPES[uri], targets, diagnostics)
    _check_schema(roots, diagnostics)


def _check_shape(roots: list[Structure], diagnostics: Diagnostics) -> None:
    if not roots or roots[0].tag != "HEAD":
        diagnostics.error("missing-head", "the dataset must start with HEAD", 1)
    heads = [r for r in roots if r.tag == "HEAD"]
    for extra in heads[1:]:
        diagnostics.error("duplicate-head", "a second HEAD is not allowed", extra.line)
    trailers = [i for i, r in enumerate(roots) if r.tag == "TRLR"]
    if not trailers:
        diagnostics.error("missing-trlr", "the dataset must end with TRLR", None)
    elif trailers[0] != len(roots) - 1:
        after = roots[trailers[0] + 1]
        diagnostics.error("after-trlr", "records after TRLR", after.line)
    for index in trailers:
        trailer = roots[index]
        if trailer.children or trailer.payload is not None or trailer.pointer is not None:
            diagnostics.error(
                "trlr-content", "TRLR takes no payload or substructures", trailer.line
            )
    if heads:
        gedc = heads[0].first("GEDC")
        version = gedc.text("VERS") if gedc is not None else None
        if version is None or not (version == "7.0" or version.startswith("7.0.")):
            diagnostics.error(
                "gedc-version", f"HEAD.GEDC.VERS must be 7.0.x, found {version!r}", heads[0].line
            )


def _collect_xrefs(roots: list[Structure], diagnostics: Diagnostics) -> dict[str, str]:
    targets: dict[str, str] = {}
    for root in roots:
        if root.xref is None:
            continue
        if root.xref in targets:
            diagnostics.error("duplicate-xref", f"{root.xref} is used twice", root.line)
            continue
        targets[root.xref] = root.tag
    return targets


def _check_node(
    node: Structure, stype: StructureType, targets: dict[str, str], diagnostics: Diagnostics
) -> None:
    stack: list[tuple[Structure, StructureType]] = [(node, stype)]
    while stack:
        current, ctype = stack.pop()
        _check_payload(current, ctype, targets, diagnostics)
        counts = Counter(child.tag for child in current.children)
        for tag, child in ctype.children.items():
            if child.required and counts[tag] == 0:
                diagnostics.error(
                    "missing-substructure", f"{current.tag} requires {tag}", current.line
                )
            if child.singular and counts[tag] > 1:
                extra = current.all(tag)[1]
                diagnostics.error(
                    "too-many", f"{current.tag} allows at most one {tag}", extra.line
                )
        for sub in current.children:
            if sub.is_extension:
                continue
            spec_child = ctype.children.get(sub.tag)
            if spec_child is None:
                diagnostics.error(
                    "not-allowed", f"{sub.tag} is not a permitted substructure of {current.tag}",
                    sub.line,
                )
                continue
            stack.append((sub, STRUCTURE_TYPES[spec_child.uri]))


def _check_payload(
    node: Structure, stype: StructureType, targets: dict[str, str], diagnostics: Diagnostics
) -> None:
    rule = stype.payload
    if rule.kind == "none":
        if node.payload is not None or node.pointer is not None:
            diagnostics.error("unexpected-payload", f"{node.tag} takes no payload", node.line)
        return
    if rule.kind == "Y":
        if node.pointer is not None or node.payload not in (None, "Y"):
            diagnostics.error(
                "payload-y", f"{node.tag} payload must be 'Y' or empty", node.line
            )
        return
    if rule.kind == "pointer":
        _check_pointer(node, rule.target, targets, diagnostics)
        return
    if node.pointer is not None:
        diagnostics.error("unexpected-pointer", f"{node.tag} takes text, not a pointer", node.line)
        return
    if node.payload is None or rule.datatype is None:
        return
    problem = check_value(rule.datatype, node.payload, stype.enum_set)
    if problem is not None:
        diagnostics.error("payload-syntax", f"{node.tag}: {problem}", node.line)


def _check_pointer(
    node: Structure, target: str | None, targets: dict[str, str], diagnostics: Diagnostics
) -> None:
    if node.pointer is None:
        diagnostics.error("expected-pointer", f"{node.tag} must point to a record", node.line)
        return
    if node.pointer == VOID:
        return
    found = targets.get(node.pointer)
    if found is None:
        diagnostics.error(
            "dangling-pointer", f"{node.tag} points to missing {node.pointer}", node.line
        )
    elif target is not None and found != target:
        diagnostics.error(
            "pointer-type", f"{node.tag} must point to a {target} record, not {found}", node.line
        )


def _check_schema(roots: list[Structure], diagnostics: Diagnostics) -> None:
    head = roots[0] if roots and roots[0].tag == "HEAD" else None
    schema = head.first("SCHMA") if head is not None else None
    if schema is None:
        return
    seen: dict[str, str] = {}
    for entry in schema.all("TAG"):
        tag, _, uri = (entry.payload or "").partition(" ")
        if not EXT_TAG_RE.match(tag):
            continue
        if tag in seen and seen[tag] != uri:
            diagnostics.error(
                "schema-duplicate", f"{tag} is defined with two URIs", entry.line
            )
        seen[tag] = uri


def undocumented_extension_tags(roots: list[Structure]) -> Counter[str]:
    """Extension tags used in the dataset but not defined in ``HEAD.SCHMA``."""
    head = roots[0] if roots and roots[0].tag == "HEAD" else None
    schema = head.first("SCHMA") if head is not None else None
    documented = set()
    if schema is not None:
        documented = {(t.payload or "").partition(" ")[0] for t in schema.all("TAG")}
    used: Counter[str] = Counter()
    for root in roots:
        for node in root.walk():
            if node.is_extension and node.tag not in documented:
                used[node.tag] += 1
    return used
