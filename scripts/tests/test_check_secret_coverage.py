"""Tests for scripts/check-secret-coverage.py."""

from __future__ import annotations

import copy
import unittest

from _load import ROOT, load

cov = load("check-secret-coverage.py")


def _deploy(docs, name):
    return next(d for d in docs if d.get("kind") in {"Deployment", "Job"} and d["metadata"]["name"] == name)


def _container(doc):
    return doc["spec"]["template"]["spec"]["containers"][0]


class SecretCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = cov.load_base(ROOT)
        cls.contract = cov.contract_env((ROOT / "docs/ARCHITECTURE.md").read_text())

    def setUp(self):
        self.docs = copy.deepcopy(self.base)

    def bites(self, fragment):
        errs = cov.check(self.docs, self.contract)
        self.assertTrue(any(fragment in e for e in errs), f"{fragment!r} not in {errs}")

    def test_contract_parsed(self):
        self.assertIn("DATABASE_URL", self.contract["api"])
        self.assertIn("FH_SESSION_SECRET", self.contract["web"])
        self.assertNotIn("FH_SESSION_SECRET", self.contract["api"])

    def test_repository_passes(self):
        self.assertEqual(cov.check(self.docs, self.contract), [])

    def test_unprovisioned_key(self):
        env = _container(_deploy(self.docs, "family-history-api"))["env"]
        ref = next(e for e in env if e["name"] == "DATABASE_URL")
        ref["valueFrom"]["secretKeyRef"]["key"] = "DATABASE_URL_TYPO"
        self.bites("does not provide")

    def test_unknown_secret(self):
        env = _container(_deploy(self.docs, "family-history-web"))["env"]
        ref = next(e for e in env if e["name"] == "FH_SESSION_SECRET")
        ref["valueFrom"]["secretKeyRef"]["name"] = "somewhere-else"
        self.bites("which no ExternalSecret")

    def test_platform_secret_cannot_grow_keys(self):
        env = _container(_deploy(self.docs, "family-history-api"))["env"]
        env.append({"name": "REDIS_URL", "valueFrom": {"secretKeyRef": {"name": "family-history-secrets", "key": "REDIS_URL"}}})
        self.bites("does not provide")

    def test_database_urls_come_from_the_platform_secret(self):
        refs = {
            (e["name"], e["valueFrom"]["secretKeyRef"]["name"])
            for d in self.docs if d.get("kind") in {"Deployment", "Job"}
            for e in _container(d).get("env", []) if "valueFrom" in e
        }
        self.assertIn(("DATABASE_URL", "family-history-secrets"), refs)
        self.assertIn(("DIRECT_DATABASE_URL", "family-history-secrets"), refs)
        self.assertFalse([r for r in refs if r[0].startswith("FH_S3_")], "no bucket secrets in the first deploy")

    def test_unused_key(self):
        job = _deploy(self.docs, "family-history-migrate")
        _container(job)["env"] = [e for e in _container(job)["env"] if e["name"] != "DIRECT_DATABASE_URL"]
        self.bites("DIRECT_DATABASE_URL is consumed by no workload")

    def test_plain_value_for_sensitive_var(self):
        env = _container(_deploy(self.docs, "family-history-web"))["env"]
        env.append({"name": "AUTH_JANUA_CLIENT_SECRET", "value": "x"})
        self.bites("must come from a secretKeyRef")

    def test_var_outside_contract(self):
        _container(_deploy(self.docs, "family-history-web"))["env"].append({"name": "DATABASE_URL", "value": "x"})
        self.bites("not in the web env contract")

    def test_envfrom_and_volume_unknown(self):
        c = _container(_deploy(self.docs, "family-history-web"))
        c["envFrom"] = [{"secretRef": {"name": "ghost"}}]
        self.bites("envFrom Secret ghost")
        spec = _deploy(self.docs, "family-history-api")["spec"]["template"]["spec"]
        spec["volumes"].append({"name": "v", "secret": {"secretName": "ghost2"}})
        self.bites("mounts Secret ghost2")


if __name__ == "__main__":
    unittest.main()
