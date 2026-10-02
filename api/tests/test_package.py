"""Smoke test: the package imports and reports its version."""

import family_history


def test_version_is_declared() -> None:
    assert family_history.__version__ == "0.1.0"
