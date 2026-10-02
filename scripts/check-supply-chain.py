#!/usr/bin/env python3
"""Supply-chain guard for the GitHub workflows and the Dockerfiles (stdlib plus PyYAML).

Fails, naming every offending file and job, when:

1. Triggers. A workflow uses ``pull_request_target`` (it runs fork code with the base repository's secrets).
2. Permissions. A workflow has no top-level ``permissions:`` block, or its top-level ``contents`` is not
   ``read`` (jobs widen what they need, one by one).
3. Runners. A job's ``runs-on`` is anything but the literal ``ubuntu-24.04``. This is a public repository:
   GitHub-hosted runners only, so fork pull requests can never reach MADFAM's self-hosted pool, and
   ``ubuntu-latest`` moves under us.
4. Timeouts. A job (other than a reusable-workflow call) has no ``timeout-minutes``.
5. Pins. A ``uses:`` reference (step action or job-level reusable workflow) is not pinned to a full
   40-hex commit SHA, or has no comment naming what the SHA stands for: ``# vX.Y.Z`` for an action, a
   ``vX...`` release or ``main`` for a reusable workflow. ``docker://`` actions and job ``services`` /
   ``container`` images must be digest-pinned (``@sha256:<64 hex>``).
6. Reusable workflows. ``secrets: inherit`` is refused (pass named secrets only). A reusable workflow that
   runs on a ``pull_request`` trigger must come from ``madfam-org`` and receive an explicit
   ``runner: ubuntu-24.04`` input, because the org workflows default to the self-hosted pool with no fork
   guard.
7. Dockerfiles. A ``FROM`` image (after resolving ``ARG`` defaults) or the ``# syntax=`` frontend is not
   digest-pinned. ``FROM scratch`` and references to an earlier build stage are fine.

Usage: ``python scripts/check-supply-chain.py [--root DIR]``. Tests: ``scripts/tests/test_check_supply_chain.py``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

RUNNER = "ubuntu-24.04"
SHA_REF = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
ACTION_COMMENT = re.compile(r"#\s*v\d[\w.\-]*")
REUSABLE_COMMENT = re.compile(r"#.*(\bv\d[\w.\-]*|\bmain\b)")
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}\b")
USES_LINE = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^\s#'\"]+)['\"]?(.*)$")
FROM_LINE = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.IGNORECASE)
ARG_LINE = re.compile(r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(\S+)", re.IGNORECASE)
SYNTAX_LINE = re.compile(r"^#\s*syntax\s*=\s*(\S+)", re.IGNORECASE)
SKIP_DIRS = {".git", "node_modules", ".venv", ".tools", ".next", "dist", "build"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def fail(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")


def _uses_comments(text: str) -> dict[str, list[str]]:
    """Map each ``uses:`` value to the trailing text of every line it appears on (to read its comment)."""
    out: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = USES_LINE.match(line)
        if m:
            out.setdefault(m.group(1), []).append(m.group(2))
    return out


def _check_uses(rep: Report, where: str, ref: str, comments: dict[str, list[str]], reusable: bool) -> None:
    if ref.startswith("./"):
        return  # a local action or workflow in this repository
    if ref.startswith("docker://"):
        if not DIGEST.search(ref):
            rep.fail(where, f"{ref}: docker:// action is not digest-pinned")
        return
    if not SHA_REF.match(ref):
        rep.fail(where, f"{ref}: not pinned to a full 40-hex commit SHA")
        return
    pattern = REUSABLE_COMMENT if reusable else ACTION_COMMENT
    trailing = comments.get(ref, [])
    if not trailing or not all(pattern.search(t) for t in trailing):
        need = "a vX release or main" if reusable else "# vX.Y.Z"
        rep.fail(where, f"{ref}: the pin needs a comment naming {need}")


def _triggers(doc: dict) -> dict:
    trig = doc.get(True, doc.get("on", {}))  # PyYAML reads the bare key `on` as True
    if isinstance(trig, str):
        return {trig: None}
    if isinstance(trig, list):
        return {t: None for t in trig}
    return trig or {}


def check_workflow(rep: Report, path: Path, rel: str) -> None:
    text = path.read_text(encoding="utf-8")
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        rep.fail(rel, f"invalid YAML: {exc}")
        return
    triggers = _triggers(doc)
    if "pull_request_target" in triggers:
        rep.fail(rel, "pull_request_target is refused")
    perms = doc.get("permissions")
    if perms is None:
        rep.fail(rel, "no top-level permissions: block (set contents: read and widen per job)")
    elif not (isinstance(perms, dict) and perms.get("contents") == "read"):
        rep.fail(rel, "top-level permissions must be exactly scoped and include contents: read")
    comments = _uses_comments(text)
    for job_id, job in (doc.get("jobs") or {}).items():
        where = f"{rel} job {job_id}"
        if not isinstance(job, dict):
            rep.fail(where, "job is not a mapping")
            continue
        if "uses" in job:
            ref = str(job["uses"])
            _check_uses(rep, where, ref, comments, reusable=True)
            if job.get("secrets") == "inherit":
                rep.fail(where, "secrets: inherit is refused; pass named secrets")
            if "pull_request" in triggers:
                if not ref.startswith("madfam-org/"):
                    rep.fail(where, "a reusable workflow on pull_request must come from madfam-org")
                if (job.get("with") or {}).get("runner") != RUNNER:
                    rep.fail(where, f"a reusable workflow on pull_request needs the input runner: {RUNNER}")
            continue
        runs_on = job.get("runs-on")
        if runs_on != RUNNER:
            rep.fail(where, f"runs-on must be the literal {RUNNER} (got {runs_on!r})")
        if "timeout-minutes" not in job:
            rep.fail(where, "no timeout-minutes")
        for svc_name, svc in (job.get("services") or {}).items():
            image = svc.get("image", "") if isinstance(svc, dict) else str(svc)
            if not DIGEST.search(str(image)):
                rep.fail(where, f"service {svc_name}: image {image!r} is not digest-pinned")
        container = job.get("container")
        if container:
            image = container.get("image", "") if isinstance(container, dict) else str(container)
            if not DIGEST.search(str(image)):
                rep.fail(where, f"container image {image!r} is not digest-pinned")
        for i, step in enumerate(job.get("steps") or []):
            if isinstance(step, dict) and "uses" in step:
                _check_uses(rep, f"{where} step {step.get('name', i)}", str(step["uses"]), comments, False)


def _resolve(image: str, args: dict[str, str]) -> str:
    return re.sub(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", lambda m: args.get(m.group(1), m.group(0)), image)


def check_dockerfile(rep: Report, path: Path, rel: str) -> None:
    args: dict[str, str] = {}
    stages: set[str] = set()
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines:
        m = SYNTAX_LINE.match(lines[0])
        if m and not DIGEST.search(m.group(1)):
            rep.fail(rel, f"# syntax={m.group(1)} is not digest-pinned")
    for n, line in enumerate(lines, start=1):
        am = ARG_LINE.match(line)
        if am:
            args.setdefault(am.group(1), am.group(2).strip("'\""))
            continue
        fm = FROM_LINE.match(line)
        if not fm:
            continue
        image = _resolve(fm.group(1), args)
        if fm.group(2):
            stages.add(fm.group(2).lower())
        if image.lower() == "scratch" or image.lower() in stages - {(fm.group(2) or "").lower()}:
            continue
        if "$" in image:
            rep.fail(f"{rel}:{n}", f"FROM {fm.group(1)} uses an ARG with no default; cannot verify its pin")
        elif not DIGEST.search(image):
            rep.fail(f"{rel}:{n}", f"FROM {image} is not digest-pinned (@sha256:...)")


def tracked_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout
        return [p for p in out.splitlines() if (root / p).is_file()]
    except (OSError, subprocess.CalledProcessError):
        found = []
        for p in root.rglob("*"):
            if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(root).parts):
                found.append(p.relative_to(root).as_posix())
        return found


def run(root: Path) -> list[str]:
    rep = Report()
    files = tracked_files(root)
    workflows = [f for f in files if re.match(r"^\.github/workflows/[^/]+\.ya?ml$", f)]
    if not workflows:
        rep.fail(".github/workflows", "no workflows found")
    for rel in sorted(workflows):
        check_workflow(rep, root / rel, rel)
    for rel in sorted(f for f in files if re.search(r"(^|/)Dockerfile[^/]*$", f)):
        check_dockerfile(rep, root / rel, rel)
    return rep.errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ns = parser.parse_args(argv)
    errors = run(ns.root.resolve())
    for e in errors:
        print(f"supply-chain: {e}", file=sys.stderr)
    if errors:
        print(f"supply-chain: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print("supply-chain: every workflow and Dockerfile is pinned and fork-safe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
