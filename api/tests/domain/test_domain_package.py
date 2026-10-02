"""Guards for the domain package: public API, purity (stdlib only, no I/O, no clock) and size."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import family_history.domain as domain

DOMAIN_DIR = Path(domain.__file__).parent
SOURCES = sorted(DOMAIN_DIR.rglob("*.py"))

_FORBIDDEN_CALLS = {"open", "today", "now", "utcnow", "time", "urlopen", "socket", "getenv"}


def test_public_api_is_explicit_and_importable() -> None:
    assert len(domain.__all__) == len(set(domain.__all__))
    for name in domain.__all__:
        assert hasattr(domain, name), name


def test_domain_imports_only_the_standard_library() -> None:
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            else:
                continue
            for root in roots:
                assert root in sys.stdlib_module_names or root == "__future__", (path, root)


def test_domain_does_no_io_and_reads_no_clock() -> None:
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                assert name not in _FORBIDDEN_CALLS, (path, node.lineno, name)


def test_source_files_stay_under_600_lines() -> None:
    for path in SOURCES:
        lines = path.read_text(encoding="utf-8").count("\n")
        assert lines < 600, (path, lines)
