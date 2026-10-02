#!/usr/bin/env python3
"""Secret-coverage guard for the production kustomize base (stdlib plus PyYAML).

Reads the resources listed in ``infra/k8s/production/kustomization.yaml`` (no kustomize needed) and fails when:

1. A workload's ``secretKeyRef`` names a Secret or key that no ExternalSecret in the repository provides
   (a key read but never provisioned is an outage that only shows up at deploy time).
2. An ``envFrom.secretRef`` or a ``secret`` volume names a Secret that no ExternalSecret produces.
3. An ExternalSecret key is consumed by no workload (custody: a secret is mounted only where it is used).
4. A sensitive variable (a database URL, a credential, the session secret, the allowlist) is set as a
   plain ``value:`` instead of a secret reference.
5. A workload sets an environment variable that is not in the env contract of docs/ARCHITECTURE.md for its
   process (api or web), apart from a short list of runtime variables (NODE_ENV, PORT, ...).

Usage: ``python scripts/check-secret-coverage.py [--root DIR]``. Tests:
``scripts/tests/test_check_secret_coverage.py``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml

BASE = Path("infra/k8s/production")
POD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}
# Process of a workload, by its app.kubernetes.io/component label.
COMPONENT_PROCESS = {"api": "api", "migrate": "api", "worker": "api", "web": "web"}
RUNTIME_VARS = {"NODE_ENV", "NEXT_TELEMETRY_DISABLED", "HOSTNAME", "PORT", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"}
SENSITIVE = {
    "DATABASE_URL", "DIRECT_DATABASE_URL", "REDIS_URL", "FH_S3_ACCESS_KEY_ID", "FH_S3_SECRET_ACCESS_KEY",
    "FH_EARLY_ACCESS_ALLOWLIST", "FH_SENTRY_DSN", "AUTH_JANUA_CLIENT_ID", "AUTH_JANUA_CLIENT_SECRET",
    "FH_SESSION_SECRET",
}

Doc = dict[str, Any]


def contract_env(architecture: str) -> dict[str, set[str]]:
    """Parse the Environment table of docs/ARCHITECTURE.md into {process: {VAR, ...}}."""
    out: dict[str, set[str]] = {}
    section = architecture.split("### Environment", 1)[-1].split("\n### ", 1)[0]
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in {"api", "web", "worker"}:
            out.setdefault(cells[0], set()).update(re.findall(r"`([A-Z][A-Z0-9_]+)`", cells[1]))
    return out


def load_base(root: Path) -> list[Doc]:
    kz = yaml.safe_load((root / BASE / "kustomization.yaml").read_text())
    docs: list[Doc] = []
    for res in kz.get("resources") or []:
        docs.extend(d for d in yaml.safe_load_all((root / BASE / res).read_text()) if isinstance(d, dict))
    return docs


def _pod(doc: Doc) -> tuple[Doc, Doc] | None:
    if doc.get("kind") not in POD_KINDS:
        return None
    spec = doc.get("spec") or {}
    if doc["kind"] == "CronJob":
        spec = (spec.get("jobTemplate") or {}).get("spec") or {}
    template = spec.get("template") or {}
    return (template.get("metadata") or {}), (template.get("spec") or {})


def check(docs: list[Doc], contract: dict[str, set[str]]) -> list[str]:
    errs: list[str] = []
    provided: dict[str, set[str]] = {}
    for d in docs:
        if d.get("kind") == "ExternalSecret":
            target = ((d.get("spec") or {}).get("target") or {}).get("name") or d["metadata"]["name"]
            keys = {item.get("secretKey") for item in (d["spec"].get("data") or [])}
            provided.setdefault(target, set()).update(k for k in keys if k)
    used: dict[str, set[str]] = {name: set() for name in provided}
    for d in docs:
        pod = _pod(d)
        if pod is None:
            continue
        meta, spec = pod
        where = f"{d['kind']}/{d['metadata']['name']}"
        component = (meta.get("labels") or {}).get("app.kubernetes.io/component", "")
        process = COMPONENT_PROCESS.get(component)
        if process is None:
            errs.append(f"{where}: unknown app.kubernetes.io/component {component!r}; cannot match the env contract")
        allowed = contract.get(process or "", set()) | RUNTIME_VARS
        for vol in spec.get("volumes") or []:
            secret = (vol.get("secret") or {}).get("secretName")
            if secret:
                if secret not in provided:
                    errs.append(f"{where}: volume {vol.get('name')} mounts Secret {secret}, which no ExternalSecret produces")
                else:
                    used[secret].update(provided[secret])
        for c in [*(spec.get("initContainers") or []), *(spec.get("containers") or [])]:
            cw = f"{where} container {c.get('name')}"
            for src in c.get("envFrom") or []:
                name = (src.get("secretRef") or {}).get("name")
                if name:
                    if name not in provided:
                        errs.append(f"{cw}: envFrom Secret {name} is produced by no ExternalSecret")
                    else:
                        used[name].update(provided[name])
                        for key in provided[name] - allowed:
                            errs.append(f"{cw}: envFrom brings {key}, which is not in the {process} env contract")
            for env in c.get("env") or []:
                var = env.get("name")
                if var not in allowed:
                    errs.append(f"{cw}: {var} is not in the {process} env contract (docs/ARCHITECTURE.md)")
                ref = (env.get("valueFrom") or {}).get("secretKeyRef")
                if ref:
                    sname, key = ref.get("name"), ref.get("key")
                    if sname not in provided:
                        errs.append(f"{cw}: {var} reads Secret {sname}, which no ExternalSecret produces")
                    elif key not in provided[sname]:
                        errs.append(f"{cw}: {var} reads key {key} that ExternalSecret target {sname} does not map")
                    else:
                        used[sname].add(key)
                elif var in SENSITIVE:
                    errs.append(f"{cw}: {var} is sensitive and must come from a secretKeyRef, never a plain value")
    for name, keys in provided.items():
        for key in sorted(keys - used.get(name, set())):
            errs.append(f"ExternalSecret target {name}: key {key} is consumed by no workload")
    return errs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check every secret reference is provisioned.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ns = parser.parse_args(argv)
    root = ns.root.resolve()
    contract = contract_env((root / "docs" / "ARCHITECTURE.md").read_text())
    if not contract.get("api") or not contract.get("web"):
        print("secret-coverage: could not read the env contract from docs/ARCHITECTURE.md", file=sys.stderr)
        return 1
    docs = load_base(root)
    errs = check(docs, contract)
    for e in errs:
        print(f"secret-coverage: {e}", file=sys.stderr)
    if errs:
        return 1
    n = sum(1 for d in docs if d.get("kind") == "ExternalSecret")
    print(f"secret-coverage: every secret reference is provisioned by the {n} ExternalSecrets, and every key is used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
