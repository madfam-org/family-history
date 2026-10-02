"""Tests for scripts/check-supply-chain.py."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from _load import ROOT, load

sc = load("check-supply-chain.py")
SHA = "11d5960a326750d5838078e36cf38b85af677262"
GOOD = f"""\
name: CI
on:
  pull_request:
  push:
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    services:
      db:
        image: postgres:16@sha256:{'a' * 64}
    steps:
      - uses: actions/checkout@{SHA} # v4.4.0
      - uses: ./.github/actions/local
  gates:
    uses: madfam-org/.github/.github/workflows/gates.yml@{SHA} # main
    with:
      runner: ubuntu-24.04
"""


class SupplyChainTest(unittest.TestCase):
    def run_on(self, workflow: str, dockerfile: str | None = None) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/ci.yml").write_text(textwrap.dedent(workflow))
            if dockerfile is not None:
                (root / "api").mkdir()
                (root / "api/Dockerfile").write_text(textwrap.dedent(dockerfile))
            return sc.run(root)

    def assertBites(self, errors: list[str], fragment: str) -> None:
        self.assertTrue(any(fragment in e for e in errors), f"{fragment!r} not in {errors}")

    def test_repository_passes(self):
        self.assertEqual(sc.run(ROOT), [])

    def test_good_workflow_passes(self):
        self.assertEqual(self.run_on(GOOD), [])

    def test_tag_pin_refused(self):
        self.assertBites(self.run_on(GOOD.replace(f"checkout@{SHA}", "checkout@v4")), "40-hex")

    def test_missing_version_comment(self):
        self.assertBites(self.run_on(GOOD.replace(" # v4.4.0", "")), "comment naming")

    def test_self_hosted_or_latest_runner_refused(self):
        self.assertBites(self.run_on(GOOD.replace("runs-on: ubuntu-24.04", "runs-on: ubuntu-latest")), "runs-on")
        self.assertBites(self.run_on(GOOD.replace("runs-on: ubuntu-24.04", "runs-on: madfam-runners-blue")), "runs-on")

    def test_timeout_required(self):
        self.assertBites(self.run_on(GOOD.replace("    timeout-minutes: 5\n", "")), "timeout-minutes")

    def test_permissions_required(self):
        self.assertBites(self.run_on(GOOD.replace("permissions:\n  contents: read\n", "")), "permissions")
        self.assertBites(self.run_on(GOOD.replace("contents: read", "contents: write")), "contents: read")

    def test_pull_request_target_refused(self):
        self.assertBites(self.run_on(GOOD.replace("  pull_request:\n", "  pull_request_target:\n")), "pull_request_target")

    def test_reusable_on_pull_request_needs_explicit_runner(self):
        self.assertBites(self.run_on(GOOD.replace("      runner: ubuntu-24.04\n", "      other: x\n")), "runner: ubuntu-24.04")

    def test_secrets_inherit_refused(self):
        self.assertBites(self.run_on(GOOD + "    secrets: inherit\n"), "secrets: inherit")

    def test_service_image_digest(self):
        self.assertBites(self.run_on(GOOD.replace(f"@sha256:{'a' * 64}", "")), "not digest-pinned")

    def test_dockerfile_from_pins(self):
        digest = "sha256:" + "b" * 64
        ok = f"""\
        # syntax=docker/dockerfile:1@{digest}
        ARG PY=python:3.12-slim@{digest}
        FROM ${{PY}} AS build
        FROM build AS runtime
        FROM scratch
        """
        self.assertEqual(self.run_on(GOOD, ok), [])
        self.assertBites(self.run_on(GOOD, "FROM python:3.12-slim\n"), "not digest-pinned")
        self.assertBites(self.run_on(GOOD, "# syntax=docker/dockerfile:1\nFROM scratch\n"), "syntax")
        self.assertBites(self.run_on(GOOD, "ARG IMG\nFROM ${IMG}\n"), "no default")


if __name__ == "__main__":
    unittest.main()
