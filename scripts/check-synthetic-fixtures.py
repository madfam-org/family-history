#!/usr/bin/env python3
"""Synthetic-data guard (stdlib only; doctrine 1 in AGENTS.md: this repository never holds a real person).

Scans every tracked text file in test, fixture and seed locations (directories named tests, test,
__tests__, fixtures, __fixtures__, seeds, seed, testdata or e2e, and files named *.test.*, *.spec.*,
test_*.py or *_test.py) and fails on:

- ``curp``:  a CURP-shaped string (18 characters with a valid date and state code);
- ``rfc``:   an RFC-shaped string (3-4 letters, a valid date, 3-character homoclave), except SAT's two
             public generic RFCs;
- ``phone``: a phone number (international ``+`` form, ``(55) 1234 5678`` or ``55-1234-5678`` forms), except
             all-zero subscriber numbers and the fictional 555-01xx range;
- ``email``: an email address outside example.com, example.org, example.net and the .test / .invalid
             top-level domains;
- ``name``:  a person name in ``api/tests/**`` (GEDCOM NAME/GIVN/SURN/NICK lines and given/surname/apellido/
             display_name style fields) that is not drawn from the synthetic lexicon,
             ``family_history.domain.synth.synthetic_lexicon()``. Until that function exists, this sub-check
             is skipped with a notice; once it exists it always runs.

Matched values are never printed in full (a real CURP in a CI log is the leak this guard prevents).
Exceptions live in ``scripts/synthetic-fixtures-allowlist.txt``, one per line, each with a ``#`` reason:
``<rule> <path-glob> <regex>  # why``.

Usage: ``python scripts/check-synthetic-fixtures.py [--root DIR]``. Tests:
``scripts/tests/test_check_synthetic_fixtures.py``.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import re
import subprocess
import sys
import unicodedata
from collections.abc import Iterable, Mapping
from pathlib import Path

SCOPE_DIRS = {"tests", "test", "__tests__", "fixtures", "__fixtures__", "seeds", "seed", "testdata", "e2e"}
SCOPE_FILE = re.compile(r"(\.(test|spec)\.[A-Za-z0-9]+$)|(^test_.*\.py$)|(_test\.py$)")
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".yaml", ".yml", ".ged", ".txt", ".md",
            ".csv", ".sql", ".toml", ".html", ".xml", ".gedcom", ".jsonl"}
NAME_SCOPE = "api/tests/"

_DATE = r"\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
_STATES = "AS|BC|BS|CC|CL|CM|CS|CH|DF|DG|GT|GR|HG|JC|MC|MN|MS|NT|NL|OC|PL|QT|QR|SP|SL|SR|TC|TS|TL|VZ|YN|ZS|NE"
CURP = re.compile(rf"\b[A-Z][AEIOUX][A-Z]{{2}}{_DATE}[HMX](?:{_STATES})[B-DF-HJ-NP-TV-Z]{{3}}[A-Z\d]\d\b")
RFC = re.compile(rf"(?<![A-Za-z0-9])[A-ZÑ&]{{3,4}}{_DATE}[A-Z\d]{{3}}(?![A-Za-z0-9])")
GENERIC_RFC = {"XAXX010101000", "XEXX010101000"}
PHONE = re.compile(
    r"(?<![\w+])(?:\+\d{1,3}[\s.-]?\(?\d{1,4}\)?(?:[\s.-]?\d{2,4}){2,4}"
    r"|\(\d{2,3}\)\s?\d{3,4}[\s.-]?\d{4}"
    r"|\d{2,3}[\s.-]\d{3,4}[\s.-]\d{4})(?![\w])"
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})")
SAFE_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
SAFE_EMAIL_TLDS = (".test", ".invalid")

NAME_FIELDS = (
    "given|given_name|given_names|surname|surnames|apellido|apellido_paterno|apellido_materno|"
    "paternal_surname|maternal_surname|nombre|nombres|nombre_de_pila|nombre_usado|display_name|"
    "first_name|last_name|full_name|nickname|apodo"
)
FIELD_VALUE = re.compile(rf"""(?i)["']?\b(?:{NAME_FIELDS})\b["']?\s*[:=]\s*\[?\s*["']([^"'\n]{{1,80}})["']""")
GEDCOM_NAME = re.compile(r"(?m)^\s*\d+\s+(?:NAME|GIVN|SURN|NICK|SPFX|NPFX|NSFX)\s+(.+?)\s*$")
PARTICLES = {"de", "del", "la", "las", "los", "y", "e", "van", "von", "da", "di", "do", "dos", "das", "le", "mc"}


def fold(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKD", s.casefold()) if not unicodedata.combining(ch))


def redact(value: str) -> str:
    return f"{value[:2]}… ({len(value)} chars)"


def in_scope(rel: str) -> bool:
    parts = rel.split("/")
    return bool(SCOPE_DIRS.intersection(parts[:-1])) or bool(SCOPE_FILE.search(parts[-1]))


def tracked_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
        return [p for p in out.splitlines() if (root / p).is_file()]
    except (OSError, subprocess.CalledProcessError):
        return [p.relative_to(root).as_posix() for p in root.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(root).parts]


def load_allowlist(path: Path) -> tuple[list[tuple[str, str, re.Pattern[str]]], list[str]]:
    entries, errors = [], []
    if not path.exists():
        return entries, errors
    for n, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, _, why = line.partition("#")
        fields = body.split(None, 2)
        if len(fields) != 3 or not why.strip():
            errors.append(f"{path.name}:{n}: entries are '<rule> <path-glob> <regex>  # reason'")
            continue
        entries.append((fields[0], fields[1], re.compile(fields[2].strip())))
    return entries, errors


def flatten(obj: object, out: set[str], depth: int = 0) -> None:
    if depth > 6:
        return
    if isinstance(obj, str):
        out.add(fold(obj))
        out.update(fold(t) for t in re.split(r"[\s/-]+", obj) if t)
    elif isinstance(obj, Mapping):
        for v in obj.values():
            flatten(v, out, depth + 1)
    elif isinstance(obj, Iterable):
        for item in obj:
            flatten(item, out, depth + 1)
    elif hasattr(obj, "__dict__"):
        flatten(vars(obj), out, depth + 1)


def load_lexicon(root: Path) -> tuple[set[str] | None, str]:
    """(lexicon, message) for the SCANNED tree's own lexicon, ``<root>/api/src/family_history/domain/synth``.

    None with a notice when that tree has no synth module yet. A ``family_history`` installed elsewhere never
    stands in for it: the module that loads must come from ``<root>/api/src``, or the check fails. Raises on a
    lexicon that exists but cannot be imported or is empty.
    """
    src = (root / "api" / "src").resolve()
    synth = src / "family_history" / "domain" / "synth"
    if not (synth.with_suffix(".py").is_file() or (synth / "__init__.py").is_file()):
        return None, "api/src/family_history/domain/synth does not exist yet"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        module = importlib.import_module("family_history.domain.synth")
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"cannot import family_history.domain.synth: missing module {exc.name!r} "
                           "(install the api package first)") from exc
    origin = Path(getattr(module, "__file__", "") or "").resolve()
    if src not in origin.parents:
        raise RuntimeError(f"family_history.domain.synth loaded from {origin}, not from {src}; "
                           "another installed copy shadows the tree being checked")
    fn = getattr(module, "synthetic_lexicon", None)
    if not callable(fn):
        return None, "family_history.domain.synth.synthetic_lexicon() does not exist yet"
    lexicon: set[str] = set()
    flatten(fn(), lexicon)
    lexicon.discard("")
    if not lexicon:
        raise RuntimeError("synthetic_lexicon() returned no names")
    return lexicon, f"{len(lexicon)} lexicon entries"


def name_tokens(text: str) -> Iterable[tuple[int, str]]:
    text = text.replace("\\n", "\n")
    for pattern in (GEDCOM_NAME, FIELD_VALUE):
        for m in pattern.finditer(text):
            value = m.group(1)
            if "{" in value or "$" in value:
                continue
            line = text.count("\n", 0, m.start(1)) + 1
            for tok in re.split(r"[\s/,.()\-\"']+", value):
                if len(tok) < 2 or not tok[0].isupper() or any(ch.isdigit() for ch in tok):
                    continue
                if tok.casefold() in PARTICLES or (tok.isupper() and len(tok) <= 4):
                    continue  # particles; GEDCOM tags and placeholder codes such as UNK or NN
                yield line, tok


def scan(root: Path, files: list[str], lexicon: set[str] | None,
         allow: list[tuple[str, str, re.Pattern[str]]]) -> list[str]:
    findings: list[str] = []

    def allowed(rule: str, rel: str, value: str) -> bool:
        return any(r == rule and fnmatch.fnmatch(rel, g) and rx.search(value) for r, g, rx in allow)

    for rel in files:
        if not in_scope(rel) or Path(rel).suffix.lower() not in TEXT_EXT:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for rule, rx in (("curp", CURP), ("rfc", RFC), ("phone", PHONE), ("email", EMAIL)):
            for m in rx.finditer(text):
                value = m.group(0)
                if rule == "rfc" and (value in GENERIC_RFC or CURP.search(text[m.start():m.start() + 18])):
                    continue
                if rule == "phone":
                    digits = re.sub(r"\D", "", value)
                    if len(digits) < 10 or set(digits[-8:]) == {"0"} or re.search(r"55501\d\d$", digits):
                        continue
                if rule == "email":
                    domain = m.group(1).lower()
                    if domain.endswith(SAFE_EMAIL_TLDS) or any(
                        domain == d or domain.endswith("." + d) for d in SAFE_EMAIL_DOMAINS
                    ):
                        continue
                if allowed(rule, rel, value):
                    continue
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{rel}:{line}: {rule}-shaped value {redact(value)}")
        if lexicon is not None and rel.startswith(NAME_SCOPE):
            for line, tok in name_tokens(text):
                if fold(tok) not in lexicon and not allowed("name", rel, tok):
                    findings.append(f"{rel}:{line}: name {redact(tok)} is not in the synthetic lexicon")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail on real-looking personal data in tests, fixtures and seeds.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ns = parser.parse_args(argv)
    root = ns.root.resolve()
    allow, errors = load_allowlist(root / "scripts" / "synthetic-fixtures-allowlist.txt")
    try:
        lexicon, note = load_lexicon(root)
    except Exception as exc:  # noqa: BLE001 - a broken lexicon must fail the build visibly
        print(f"synthetic-fixtures: {exc}", file=sys.stderr)
        return 1
    if lexicon is None:
        print(f"::notice title=synthetic name check skipped::{note}; the name sub-check runs once it exists")
    files = tracked_files(root)
    findings = errors + scan(root, files, lexicon, allow)
    for f in findings:
        print(f"synthetic-fixtures: {f}", file=sys.stderr)
    if findings:
        print(f"synthetic-fixtures: {len(findings)} finding(s); use the synthetic generator and lexicon",
              file=sys.stderr)
        return 1
    scanned = sum(1 for f in files if in_scope(f))
    print(f"synthetic-fixtures: {scanned} test/fixture/seed files clean"
          + (f" (names checked against {note})" if lexicon is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
