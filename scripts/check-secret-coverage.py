#!/usr/bin/env python3
"""Secret-coverage guard for the production kustomize base (stdlib plus PyYAML).

Reads the resources listed in ``infra/k8s/production/kustomization.yaml`` (no kustomize needed) and fails when:

1. A workload's ``secretKeyRef`` names a Secret or key that no ExternalSecret in the repository provides,
   and that is not one of the platform-written keys in ``PLATFORM_SECRETS`` (a key read but never
   provisioned is an outage that only shows up at deploy time).
2. An ``envFrom.secretRef`` or a ``secret`` volume names a Secret that no ExternalSecret produces.
3. An ExternalSecret or platform key is consumed by no workload (custody: a secret is mounted only where it
   is used).
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
# Secrets the platform writes outside this repository, with exactly the keys it writes. The project Secret
# from `enclii onboard --secret-name family-history-secrets --secrets-file <env>` (the creator-census
# precedent): the pooled and the direct database URL.
PLATFORM_SECRETS = {"family-history-secrets": {"DATABASE_URL", "DIRECT_DATABASE_URL"}}
SENSITIVE = {
    "DATABASE_URL", "DIRECT_DATABASE_URL", "REDIS_URL", "FH_S3_ACCESS_KEY_ID", "FH_S3_SECRET_ACCESS_KEY",
    "FH_EARLY_ACCESS_ALLOWLIST", "FH_SENTRY_DSN", "AUTH_JANUA_CLIENT_ID", "AUTH_JANUA_CLIENT_SECRET",
    "FH_SESSION_SECRET",
}

Doc = dict[str, Any]


def field(obj: Any, name: str) -> Any:
    """Read a manifest field. These scripts only ever see reference NAMES (Secret names, keys, env names);
    manifests hold no secret values, and the guards would fail if they did."""
    return obj.get(name) if isinstance(obj, dict) else None


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
    provided: dict[str, set[str]] = {name: set(keys) for name, keys in PLATFORM_SECRETS.items()}
    for d in docs:
        if d.get("kind") == "ExternalSecret":
            target = ((d.get("spec") or {}).get("target") or {}).get("name") or d["metadata"]["name"]
            keys = {field(item, "secretKey") for item in (d["spec"].get("data") or [])}
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
            target = field(field(vol, "secret"), "secretName")
            if target:
                if target not in provided:
                    errs.append(f"{where}: volume {vol.get('name')} mounts Secret {target}, which no ExternalSecret produces")
                else:
                    used[target].update(provided[target])
        for c in [*(spec.get("initContainers") or []), *(spec.get("containers") or [])]:
            cw = f"{where} container {c.get('name')}"
            for src in c.get("envFrom") or []:
                name = field(field(src, "secretRef"), "name")
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
                ref = field(field(env, "valueFrom"), "secretKeyRef")
                if ref:
                    target, key = field(ref, "name"), field(ref, "key")
                    if target not in provided:
                        errs.append(f"{cw}: {var} reads Secret {target}, which no ExternalSecret or platform write produces")
                    elif key not in provided[target]:
                        errs.append(f"{cw}: {var} reads key {key} that Secret {target} does not provide")
                    else:
                        used[target].add(key)
                elif var in SENSITIVE:
                    errs.append(f"{cw}: {var} is sensitive and must come from a secretKeyRef, never a plain value")
    for name, keys in provided.items():
        for key in sorted(keys - used.get(name, set())):
            errs.append(f"Secret {name}: key {key} is consumed by no workload")
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
    print(f"secret-coverage: every secret reference is provisioned by the {n} ExternalSecrets or the platform "
          f"Secrets ({', '.join(sorted(PLATFORM_SECRETS))}), and every key is used")
    return 0


if __name__ == "__main__":
    sys.exit(main())
