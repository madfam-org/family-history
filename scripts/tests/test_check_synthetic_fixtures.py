"""Tests for scripts/check-synthetic-fixtures.py.

Real-looking values are assembled at runtime from fragments, so this file never holds one itself and the
guard can scan it like every other test file.
"""

from __future__ import annotations

import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path

from _load import ROOT, load

sf = load("check-synthetic-fixtures.py")

CURP_VALUE = "GO" + "MA" + "800101" + "HDF" + "RRN" + "09"
RFC_VALUE = "GO" + "MA" + "800101" + "AB1"
PHONE_VALUE = "+52 " + "55 " + "1234 " + "5678"
EMAIL_VALUE = "ana" + "@" + "gmail" + ".com"


def _forget_package() -> None:
    for name in [m for m in sys.modules if m == "family_history" or m.startswith("family_history.")]:
        del sys.modules[name]


class SyntheticFixturesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "api/tests/fixtures").mkdir(parents=True)
        (self.root / "scripts").mkdir()
        _forget_package()

    def tearDown(self):
        _forget_package()
        src = str(self.root / "api" / "src")
        while src in sys.path:
            sys.path.remove(src)
        self.tmp.cleanup()

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))

    def run_guard(self) -> int:
        return sf.main(["--root", str(self.root)])

    def findings(self, lexicon=None) -> list[str]:
        files = sf.tracked_files(self.root)
        allow, errors = sf.load_allowlist(self.root / "scripts" / "synthetic-fixtures-allowlist.txt")
        return errors + sf.scan(self.root, files, lexicon, allow)

    def test_repository_passes(self):
        self.assertEqual(sf.main(["--root", str(ROOT)]), 0)

    def test_identifiers_contacts_flagged_and_redacted(self):
        self.write("api/tests/fixtures/people.json",
                   f'{{"curp": "{CURP_VALUE}", "rfc": "{RFC_VALUE}", "tel": "{PHONE_VALUE}", "mail": "{EMAIL_VALUE}"}}')
        found = self.findings()
        for rule in ("curp-shaped", "rfc-shaped", "phone-shaped", "email-shaped"):
            self.assertTrue(any(rule in f for f in found), f"{rule} not in {found}")
        self.assertFalse(any(CURP_VALUE in f or EMAIL_VALUE in f for f in found), "values must be redacted")

    def test_safe_values_pass(self):
        self.write("apps/web/src/lib/x.test.ts",
                   'const a = "ana@example.com"; const b = "x@family.test"; const c = "+52 55 0000 0000";'
                   ' const rfc = "XAXX010101000"; const d = "2026-10-01"; const ts = 1727740800;')
        self.assertEqual(self.findings(), [])

    def test_out_of_scope_ignored(self):
        self.write("api/src/family_history/notes.py", f'X = "{EMAIL_VALUE}"\n')
        self.assertEqual(self.findings(), [])

    def test_allowlist_needs_reason(self):
        self.write("api/tests/fixtures/a.json", f'{{"mail": "{EMAIL_VALUE}"}}')
        self.write("scripts/synthetic-fixtures-allowlist.txt", "email api/tests/* gmail\n")
        self.assertTrue(any("reason" in f for f in self.findings()))
        self.write("scripts/synthetic-fixtures-allowlist.txt", "email api/tests/* gmail  # parser test only\n")
        self.assertEqual(self.findings(), [])

    def test_names_skipped_until_lexicon_exists(self):
        # Hermetic: the temp tree has no synth module. A lexicon that is importable from elsewhere (an
        # installed api package, or this stand-in planted in sys.modules) must not be used for it.
        stand_in = types.ModuleType("family_history.domain.synth")
        stand_in.synthetic_lexicon = lambda: ["Ana"]  # type: ignore[attr-defined]
        sys.modules["family_history.domain.synth"] = stand_in
        self.write("api/tests/fixtures/tree.ged", "0 @I1@ INDI\n1 NAME Zacarías /Quintanilla/\n")
        lexicon, note = sf.load_lexicon(self.root)
        self.assertIsNone(lexicon)
        self.assertIn("does not exist yet", note)
        self.assertEqual(self.run_guard(), 0)

    def test_shadowing_copy_fails(self):
        self.write("api/src/family_history/__init__.py", "")
        self.write("api/src/family_history/domain/__init__.py", "")
        self.write("api/src/family_history/domain/synth.py", "def synthetic_lexicon():\n    return ['Ana']\n")
        stand_in = types.ModuleType("family_history.domain.synth")
        stand_in.__file__ = "/elsewhere/family_history/domain/synth.py"
        stand_in.synthetic_lexicon = lambda: ["Ana"]  # type: ignore[attr-defined]
        sys.modules["family_history.domain.synth"] = stand_in
        self.assertEqual(self.run_guard(), 1)

    def test_names_checked_against_lexicon(self):
        self.write("api/src/family_history/__init__.py", "")
        self.write("api/src/family_history/domain/__init__.py", "")
        self.write("api/src/family_history/domain/synth.py", """\
            def synthetic_lexicon():
                return {"given": ["Ana", "José"], "surnames": ("Ríos", "de la Peña")}
            """)
        self.write("api/tests/fixtures/ok.ged", "0 @I1@ INDI\n1 NAME Ana /Ríos de la Peña/\n2 GIVN Jose\n")
        self.write("api/tests/test_people.py", 'person = {"given": "Ana", "apellido_paterno": "Rios"}\n')
        self.assertEqual(self.run_guard(), 0)
        self.write("api/tests/test_bad.py", 'p = dict(display_name="Zacarías Quintanilla")\n')
        _forget_package()
        self.assertEqual(self.run_guard(), 1)

    def test_broken_lexicon_fails(self):
        self.write("api/src/family_history/__init__.py", "")
        self.write("api/src/family_history/domain/__init__.py", "")
        self.write("api/src/family_history/domain/synth.py", "import not_installed_dependency_xyz\n")
        self.assertEqual(self.run_guard(), 1)


if __name__ == "__main__":
    unittest.main()
