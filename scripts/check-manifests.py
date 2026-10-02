#!/usr/bin/env python3
"""Production manifest guard (stdlib plus PyYAML).

Reads the RENDERED kustomize output (``kustomize build infra/k8s/production``) plus ``kustomization.yaml``,
``enclii.yaml`` and ``docs/RUNBOOK.md``, and fails, naming each object, when:

1. Objects. The render holds a Namespace or an Ingress (the platform owns the namespace; the tunnel is the
   only edge).
2. Pods (Deployment, StatefulSet, DaemonSet, Job, CronJob). The pod is not non-root as uid 1001, mounts the
   service-account token, uses host namespaces, host paths or host ports; or a container lacks a read-only
   root filesystem, ``allowPrivilegeEscalation: false``, ``capabilities.drop: [ALL]`` (with nothing added),
   CPU and memory requests and a memory limit.
3. Probes. A Deployment container has no liveness or readiness probe, or one with ``timeoutSeconds`` < 3.
4. Images. A rendered image is not digest-pinned or carries ``:latest``, or its repository has no entry
   (name == newName, ``sha256:<64 hex>`` digest) in the kustomization ``images:`` block that the
   build-publish workflow rewrites.
5. Network. There is no default-deny policy for every pod; a peer combines selectors; the
   ``cloudflare-tunnel`` namespace reaches anything but the web on 3000 and the API on 8000; or the metrics
   port is reachable from anywhere but the ``monitoring`` namespace.
6. Routing. An enclii.yaml Service with domains has no Kubernetes Service of the same name on port 80, a
   domain is not pinned to port 80, its tunnel ingress port is not the contract port, or a tunnel-routed
   Service exposes the metrics port.
7. ExternalSecrets. A remote key is not ``secret/<namespace>``, a property is not lowercase, or an entry
   leaves conversionStrategy / decodingStrategy / metadataPolicy implicit.
8. Alerts. A PrometheusRule alert has no severity, or no runbook_url pointing at an existing anchor of
   docs/RUNBOOK.md.

Usage:
  kustomize build infra/k8s/production > /tmp/render.yaml
  python scripts/check-manifests.py /tmp/render.yaml [--extract-rules OUT.yaml]
``--extract-rules`` writes the PrometheusRule groups as a plain rules file for ``promtool check rules``.
Tests: ``scripts/tests/test_check_manifests.py``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = Path("infra/k8s/production")
NAMESPACE = "family-history"
UID = 1001
# Workload -> the only port the tunnel may reach on it (docs/ARCHITECTURE.md, Contracts).
TUNNEL_PORTS = {"family-history-web": 3000, "family-history-api": 8000}
METRICS_PORT = 9090
RUNBOOK_URL = "https://github.com/madfam-org/family-history/blob/main/docs/RUNBOOK.md#"
POD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
NAME_LABEL = "app.kubernetes.io/name"

Doc = dict[str, Any]


def _name(doc: Doc) -> str:
    return f"{doc.get('kind')}/{(doc.get('metadata') or {}).get('name')}"


def pod_spec(doc: Doc) -> Doc | None:
    spec = doc.get("spec") or {}
    if doc.get("kind") == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec")) or {}
    return ((spec.get("template") or {}).get("spec")) if doc.get("kind") in POD_KINDS else None


def github_anchor(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def runbook_anchors(text: str) -> set[str]:
    return {github_anchor(m.group(1)) for m in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, re.M)}


def check_pods(docs: list[Doc], errs: list[str]) -> None:
    for doc in docs:
        spec = pod_spec(doc)
        if spec is None:
            continue
        where = _name(doc)
        psc = spec.get("securityContext") or {}
        if psc.get("runAsNonRoot") is not True or psc.get("runAsUser") != UID:
            errs.append(f"{where}: pod securityContext must set runAsNonRoot: true and runAsUser: {UID}")
        if spec.get("automountServiceAccountToken") is not False:
            errs.append(f"{where}: automountServiceAccountToken must be false")
        for key in ("hostNetwork", "hostPID", "hostIPC"):
            if spec.get(key):
                errs.append(f"{where}: {key} is forbidden")
        for vol in spec.get("volumes") or []:
            if "hostPath" in vol:
                errs.append(f"{where}: hostPath volume {vol.get('name')} is forbidden")
        containers = [*(spec.get("initContainers") or []), *(spec.get("containers") or [])]
        if not containers:
            errs.append(f"{where}: no containers")
        for c in containers:
            cw = f"{where} container {c.get('name')}"
            sc = c.get("securityContext") or {}
            if sc.get("readOnlyRootFilesystem") is not True:
                errs.append(f"{cw}: readOnlyRootFilesystem must be true")
            if sc.get("allowPrivilegeEscalation") is not False:
                errs.append(f"{cw}: allowPrivilegeEscalation must be false")
            if sc.get("privileged"):
                errs.append(f"{cw}: privileged is forbidden")
            caps = sc.get("capabilities") or {}
            if "ALL" not in (caps.get("drop") or []) or caps.get("add"):
                errs.append(f"{cw}: capabilities must drop ALL and add nothing")
            if sc.get("runAsUser", UID) != UID or sc.get("runAsNonRoot") is False:
                errs.append(f"{cw}: container securityContext must not override uid {UID} or non-root")
            res = c.get("resources") or {}
            req, lim = res.get("requests") or {}, res.get("limits") or {}
            if not (req.get("cpu") and req.get("memory") and lim.get("memory")):
                errs.append(f"{cw}: needs resources.requests.cpu, requests.memory and limits.memory")
            for port in c.get("ports") or []:
                if "hostPort" in port:
                    errs.append(f"{cw}: hostPort is forbidden")
            image = str(c.get("image", ""))
            if "@sha256:" not in image or image.split("@")[0].endswith(":latest"):
                errs.append(f"{cw}: image {image!r} is not digest-pinned (kustomization images: block)")
            if doc.get("kind") == "Deployment":
                for probe in ("livenessProbe", "readinessProbe"):
                    p = c.get(probe)
                    if not p:
                        errs.append(f"{cw}: no {probe}")
                    elif int(p.get("timeoutSeconds", 1)) < 3:
                        errs.append(f"{cw}: {probe}.timeoutSeconds must be >= 3")


def check_images(docs: list[Doc], kustomization: Doc, errs: list[str]) -> None:
    entries = {e.get("name"): e for e in kustomization.get("images") or []}
    for name, e in entries.items():
        if e.get("newName") != name or not DIGEST_RE.match(str(e.get("digest", ""))):
            errs.append(f"kustomization images: {name} needs newName == name and a sha256:<64 hex> digest")
    for doc in docs:
        spec = pod_spec(doc)
        for c in [*((spec or {}).get("initContainers") or []), *((spec or {}).get("containers") or [])]:
            repo = str(c.get("image", "")).split("@")[0]
            if repo not in entries:
                errs.append(f"{_name(doc)}: image {repo} has no entry in the kustomization images: block")


def _peers_ok(peers: list[Doc], where: str, errs: list[str]) -> None:
    for peer in peers:
        keys = {k for k in ("namespaceSelector", "podSelector", "ipBlock") if k in peer}
        if len(keys) != 1:
            errs.append(f"{where}: each peer must use exactly one selector (got {sorted(keys) or 'none'})")


def _selected_names(policy: Doc) -> set[str] | None:
    """The app.kubernetes.io/name values a policy selects, or None when it selects more broadly."""
    sel = (policy.get("spec") or {}).get("podSelector") or {}
    labels = sel.get("matchLabels") or {}
    if NAME_LABEL in labels and not sel.get("matchExpressions"):
        return {labels[NAME_LABEL]}
    exprs = sel.get("matchExpressions") or []
    if not labels and len(exprs) == 1 and exprs[0].get("key") == NAME_LABEL and exprs[0].get("operator") == "In":
        return set(exprs[0].get("values") or [])
    return None


def check_network(docs: list[Doc], errs: list[str]) -> None:
    policies = [d for d in docs if d.get("kind") == "NetworkPolicy"]
    default_deny = [
        p for p in policies
        if (p["spec"].get("podSelector") or {}).get("matchLabels") == {"app.kubernetes.io/part-of": NAMESPACE}
        and set(p["spec"].get("policyTypes") or []) == {"Ingress", "Egress"}
        and not p["spec"].get("ingress") and not p["spec"].get("egress")
    ]
    if not default_deny:
        errs.append("NetworkPolicy: no default-deny (Ingress and Egress) selecting every family-history pod")
    tunnel_reach: dict[str, set[int]] = {}
    for p in policies:
        where = _name(p)
        spec = p.get("spec") or {}
        for rule in spec.get("egress") or []:
            _peers_ok(rule.get("to") or [], where, errs)
        for rule in spec.get("ingress") or []:
            peers = rule.get("from") or []
            _peers_ok(peers, where, errs)
            ports = {int(x.get("port")) for x in rule.get("ports") or [] if x.get("port") is not None}
            ns_names = {
                ((peer.get("namespaceSelector") or {}).get("matchLabels") or {}).get("kubernetes.io/metadata.name")
                for peer in peers
            }
            selected = _selected_names(p)
            if "cloudflare-tunnel" in ns_names:
                if selected is None or len(selected) != 1 or not ports:
                    errs.append(f"{where}: a tunnel rule must select one workload by {NAME_LABEL} and name its port")
                    continue
                (workload,) = selected
                allowed = TUNNEL_PORTS.get(workload)
                if allowed is None or ports != {allowed}:
                    errs.append(f"{where}: the tunnel may reach only {TUNNEL_PORTS}; got {workload} on {sorted(ports)}")
                tunnel_reach.setdefault(workload, set()).update(ports)
            if not peers or not ports:
                errs.append(f"{where}: an ingress rule must name both its peers and its ports")
            if METRICS_PORT in ports and ns_names != {"monitoring"}:
                errs.append(f"{where}: port {METRICS_PORT} may be reached from the monitoring namespace only")
    for workload, port in TUNNEL_PORTS.items():
        if tunnel_reach.get(workload) != {port}:
            errs.append(f"NetworkPolicy: no tunnel ingress for {workload} on {port}")


def check_routing(docs: list[Doc], enclii_docs: list[Doc], errs: list[str]) -> None:
    services = {d["metadata"]["name"]: d for d in docs if d.get("kind") == "Service"}
    for ed in enclii_docs:
        if ed.get("kind") != "Service":
            continue
        name = ed["metadata"]["name"]
        spec = ed.get("spec") or {}
        domains = spec.get("domains") or []
        for net in ((spec.get("network") or {}).get("services")) or []:
            if "cloudflare-tunnel" in (net.get("ingress") or []) and net.get("port") != TUNNEL_PORTS.get(net.get("name")):
                errs.append(f"enclii.yaml {name}: tunnel ingress port {net.get('port')} is not the contract port")
        if not domains:
            continue
        for dom in domains:
            if dom.get("port") != 80:
                errs.append(f"enclii.yaml {name}: domain {dom.get('name')} must pin port: 80")
        svc = services.get(name)
        if svc is None:
            errs.append(f"enclii.yaml {name}: no Kubernetes Service of the same name (the tunnel route target)")
            continue
        ports = svc["spec"].get("ports") or []
        if 80 not in {p.get("port") for p in ports}:
            errs.append(f"Service/{name}: the tunnel-routed Service must publish port 80")
        if any(p.get("port") == METRICS_PORT or p.get("targetPort") in (METRICS_PORT, "metrics") for p in ports):
            errs.append(f"Service/{name}: a tunnel-routed Service must not expose the metrics port")


def check_external_secrets(docs: list[Doc], errs: list[str]) -> None:
    for doc in docs:
        if doc.get("kind") != "ExternalSecret":
            continue
        for item in (doc.get("spec") or {}).get("data") or []:
            ref = item.get("remoteRef") or {}
            where = f"{_name(doc)} {item.get('secretKey')}"
            if ref.get("key") != f"secret/{NAMESPACE}":
                errs.append(f"{where}: remote key must be secret/{NAMESPACE}")
            if not re.fullmatch(r"[a-z0-9_]+", str(ref.get("property", ""))):
                errs.append(f"{where}: property must be lowercase (the intake lowercases keys)")
            for key, want in (("conversionStrategy", "Default"), ("decodingStrategy", "None"), ("metadataPolicy", "None")):
                if ref.get(key) != want:
                    errs.append(f"{where}: set {key}: {want} explicitly")


def check_alerts(docs: list[Doc], runbook: str, errs: list[str]) -> None:
    anchors = runbook_anchors(runbook)
    for doc in docs:
        if doc.get("kind") != "PrometheusRule":
            continue
        for group in (doc.get("spec") or {}).get("groups") or []:
            for rule in group.get("rules") or []:
                if "alert" not in rule:
                    continue
                where = f"{_name(doc)} alert {rule['alert']}"
                if not (rule.get("labels") or {}).get("severity"):
                    errs.append(f"{where}: no severity label")
                url = str((rule.get("annotations") or {}).get("runbook_url", ""))
                if not url.startswith(RUNBOOK_URL):
                    errs.append(f"{where}: runbook_url must start with {RUNBOOK_URL}")
                elif url[len(RUNBOOK_URL):] not in anchors:
                    errs.append(f"{where}: docs/RUNBOOK.md has no anchor #{url[len(RUNBOOK_URL):]}")


def check(docs: list[Doc], kustomization: Doc, enclii_docs: list[Doc], runbook: str) -> list[str]:
    errs: list[str] = []
    for doc in docs:
        if doc.get("kind") in {"Namespace", "Ingress"}:
            errs.append(f"{_name(doc)}: Namespace and Ingress objects are forbidden")
    check_pods(docs, errs)
    check_images(docs, kustomization, errs)
    check_network(docs, errs)
    check_routing(docs, enclii_docs, errs)
    check_external_secrets(docs, errs)
    check_alerts(docs, runbook, errs)
    return errs


def load_all(text: str) -> list[Doc]:
    return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]


def render_without_kustomize(root: Path) -> list[Doc]:
    """A minimal stand-in for `kustomize build` (namespace + images), used by the tests only."""
    kz = yaml.safe_load((root / BASE / "kustomization.yaml").read_text())
    images = {e["name"]: e for e in kz.get("images") or []}
    docs: list[Doc] = []
    for res in kz.get("resources") or []:
        for doc in load_all((root / BASE / res).read_text()):
            doc.setdefault("metadata", {})["namespace"] = kz.get("namespace")
            spec = pod_spec(doc)
            for c in [*((spec or {}).get("initContainers") or []), *((spec or {}).get("containers") or [])]:
                repo = str(c["image"]).split("@")[0].rsplit(":", 1)[0]
                if repo in images:
                    c["image"] = f"{images[repo]['newName']}@{images[repo]['digest']}"
            docs.append(doc)
    return docs


def extract_rules(docs: list[Doc]) -> Doc:
    groups: list[Doc] = []
    for doc in docs:
        if doc.get("kind") == "PrometheusRule":
            groups.extend((doc.get("spec") or {}).get("groups") or [])
    return {"groups": groups}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the rendered production manifests.")
    parser.add_argument("rendered", help="kustomize build output ('-' for stdin)")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--extract-rules", type=Path, help="write the alert groups for promtool")
    ns = parser.parse_args(argv)
    text = sys.stdin.read() if ns.rendered == "-" else Path(ns.rendered).read_text()
    docs = load_all(text)
    root = ns.root.resolve()
    kustomization = yaml.safe_load((root / BASE / "kustomization.yaml").read_text())
    enclii_docs = load_all((root / "enclii.yaml").read_text())
    runbook_path = root / "docs" / "RUNBOOK.md"
    runbook = runbook_path.read_text() if runbook_path.exists() else ""
    errs = check(docs, kustomization, enclii_docs, runbook)
    if ns.extract_rules:
        ns.extract_rules.write_text(yaml.safe_dump(extract_rules(docs), sort_keys=False))
    for e in errs:
        print(f"check-manifests: {e}", file=sys.stderr)
    if errs:
        print(f"check-manifests: {len(errs)} problem(s) in {len(docs)} objects", file=sys.stderr)
        return 1
    print(f"check-manifests: {len(docs)} objects pass every rule")
    return 0


if __name__ == "__main__":
    sys.exit(main())
