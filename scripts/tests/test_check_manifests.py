"""Tests for scripts/check-manifests.py: the repository's own manifests pass, and each rule bites."""

from __future__ import annotations

import copy
import unittest

import yaml
from _load import ROOT, load

cm = load("check-manifests.py")


def _find(docs, kind, name):
    for d in docs:
        if d.get("kind") == kind and d["metadata"]["name"] == name:
            return d
    raise KeyError(f"{kind}/{name}")


class CheckManifestsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_docs = cm.render_without_kustomize(ROOT)
        cls.kz = yaml.safe_load((ROOT / "infra/k8s/production/kustomization.yaml").read_text())
        cls.enclii = cm.load_all((ROOT / "enclii.yaml").read_text())
        cls.runbook = (ROOT / "docs/RUNBOOK.md").read_text()

    def setUp(self):
        self.docs = copy.deepcopy(self.base_docs)

    def errors(self, docs=None, kz=None, enclii=None, runbook=None):
        return cm.check(
            self.docs if docs is None else docs,
            self.kz if kz is None else kz,
            self.enclii if enclii is None else enclii,
            self.runbook if runbook is None else runbook,
        )

    def assertBites(self, fragment):
        errs = self.errors()
        self.assertTrue(any(fragment in e for e in errs), f"expected {fragment!r} in {errs}")

    def test_repository_manifests_pass(self):
        self.assertEqual(self.errors(), [])

    def test_namespace_and_ingress_refused(self):
        self.docs.append({"kind": "Ingress", "metadata": {"name": "x"}})
        self.assertBites("Namespace and Ingress objects are forbidden")

    def test_root_and_writable_root_refused(self):
        api = _find(self.docs, "Deployment", "family-history-api")
        api["spec"]["template"]["spec"]["securityContext"]["runAsUser"] = 0
        c = api["spec"]["template"]["spec"]["containers"][0]
        c["securityContext"]["readOnlyRootFilesystem"] = False
        c["securityContext"]["capabilities"] = {"drop": ["NET_RAW"]}
        errs = self.errors()
        for frag in ("runAsUser: 1001", "readOnlyRootFilesystem", "drop ALL"):
            self.assertTrue(any(frag in e for e in errs), frag)

    def test_job_needs_resources(self):
        job = _find(self.docs, "Job", "family-history-migrate")
        del job["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
        self.assertBites("limits.memory")

    def test_probe_timeout(self):
        web = _find(self.docs, "Deployment", "family-history-web")
        web["spec"]["template"]["spec"]["containers"][0]["readinessProbe"]["timeoutSeconds"] = 1
        self.assertBites("readinessProbe.timeoutSeconds")
        del web["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]
        self.assertBites("no livenessProbe")

    def test_unpinned_image_and_missing_kustomize_entry(self):
        web = _find(self.docs, "Deployment", "family-history-web")
        web["spec"]["template"]["spec"]["containers"][0]["image"] = "ghcr.io/madfam-org/other:latest"
        errs = self.errors()
        self.assertTrue(any("not digest-pinned" in e for e in errs))
        self.assertTrue(any("no entry in the kustomization" in e for e in errs))
        kz = copy.deepcopy(self.kz)
        kz["images"][0]["digest"] = "sha256:abc"
        self.assertTrue(any("64 hex" in e for e in self.errors(kz=kz)))

    def test_tunnel_cannot_reach_metrics_or_other_ports(self):
        pol = _find(self.docs, "NetworkPolicy", "allow-tunnel-ingress-api")
        pol["spec"]["ingress"][0]["ports"].append({"protocol": "TCP", "port": 9090})
        errs = self.errors()
        self.assertTrue(any("the tunnel may reach only" in e for e in errs), errs)
        self.assertTrue(any("monitoring namespace only" in e for e in errs), errs)

    def test_tunnel_to_unknown_workload(self):
        pol = _find(self.docs, "NetworkPolicy", "allow-tunnel-ingress-web")
        pol["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/name"] = "family-history-migrate"
        self.assertBites("the tunnel may reach only")

    def test_combined_selector_refused(self):
        pol = _find(self.docs, "NetworkPolicy", "allow-web-to-api-ingress")
        pol["spec"]["ingress"][0]["from"][0]["namespaceSelector"] = {"matchLabels": {"a": "b"}}
        self.assertBites("exactly one selector")

    def test_default_deny_required(self):
        self.docs = [d for d in self.docs if d["metadata"]["name"] != "default-deny-all"]
        self.assertBites("no default-deny")

    def test_routing_rules(self):
        enclii = copy.deepcopy(self.enclii)
        enclii[1]["spec"]["domains"][0]["port"] = 3000
        self.assertTrue(any("must pin port: 80" in e for e in self.errors(enclii=enclii)))
        svc = _find(self.docs, "Service", "family-history-api")
        svc["spec"]["ports"].append({"name": "metrics", "port": 9090, "targetPort": "metrics"})
        self.assertBites("must not expose the metrics port")

    def test_external_secret_rules(self):
        es = _find(self.docs, "ExternalSecret", "family-history-web")
        es["spec"]["data"][0]["remoteRef"]["property"] = "AUTH_JANUA_CLIENT_ID"
        del es["spec"]["data"][1]["remoteRef"]["decodingStrategy"]
        es["spec"]["data"][2]["remoteRef"]["key"] = "secret/other"
        errs = self.errors()
        for frag in ("lowercase", "decodingStrategy", "secret/family-history"):
            self.assertTrue(any(frag in e for e in errs), frag)

    def test_alerts_need_runbook_anchor(self):
        self.assertTrue(any("no anchor" in e for e in self.errors(runbook="# Runbook\n")))

    def test_anchor_slug(self):
        self.assertEqual(cm.github_anchor("FamilyHistoryApiDown"), "familyhistoryapidown")
        self.assertEqual(cm.github_anchor("Public hosts"), "public-hosts")

    def test_extract_rules(self):
        groups = cm.extract_rules(self.docs)["groups"]
        self.assertTrue(groups and all("rules" in g for g in groups))


if __name__ == "__main__":
    unittest.main()
