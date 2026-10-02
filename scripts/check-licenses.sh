#!/usr/bin/env bash
# Licence gate for the runtime dependencies of the API (Python) and the web app (Node).
#
# family-history is AGPL-3.0-only, so:
#   allowed   permissive licences (MIT, BSD, Apache-2.0, ISC, PSF, MPL-2.0, Zlib, CC0, ...);
#   review    copyleft that is compatible with AGPL-3.0 (GPL-3.0, AGPL-3.0, LGPL, GPL-2.0-or-later,
#             EPL-2.0): printed, and the build passes; keep each one a deliberate choice;
#   denied    licences that are incompatible with AGPL-3.0 or not free: GPL-2.0-only, CDDL, EPL-1.0,
#             SSPL, BUSL, Commons Clause, Elastic, non-commercial, proprietary or UNLICENSED, the JSON
#             licence. The build fails;
#   unknown   no recognisable licence metadata. The build fails until the package gets a line in
#             scripts/license-overrides.txt (<ecosystem> <package> <SPDX expression>  # where it was verified).
# "A OR B" (and ";"-separated classifiers) passes when any alternative passes; "A AND B" needs all.
#
# Usage:
#   scripts/check-licenses.sh                 Python (pip-licenses on $TARGET_PYTHON's environment) and,
#                                             when apps/web/package.json exists, Node (pnpm licenses --prod)
#   scripts/check-licenses.sh --python-only | --node-only
#   scripts/check-licenses.sh --self-test     classify a fixture set and check every category
# Environment: TARGET_PYTHON (default python3), PIP_LICENSES (default pip-licenses).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

evaluate() { # evaluate <rows.json> <overrides-file> [expect-file]
  "$PY" - "$@" <<'PY'
import json, re, sys
rows = json.load(open(sys.argv[1]))
overrides = {}
for n, raw in enumerate(open(sys.argv[2]).read().splitlines() if sys.argv[2] != "-" else [], 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    body, _, why = line.partition("#")
    parts = body.split(None, 2)
    if len(parts) != 3 or not why.strip():
        sys.exit(f"license-overrides.txt:{n}: entries are '<ecosystem> <package> <SPDX>  # source'")
    overrides[(parts[0], parts[1].lower())] = parts[2].strip()
SELF = {("python", "family-history-api"), ("node", "@family-history/web")}
TOOLING = {"pip", "setuptools", "wheel", "pip-licenses", "prettytable", "wcwidth", "tomli"}
DENY = re.compile(r"SSPL|Server Side Public|BUSL|Business Source|Commons Clause|Non-?Commercial|\bNC\b|"
                  r"Elastic License|Proprietary|CDDL|Common Development and Distribution|EPL-1\.0|"
                  r"Eclipse Public License 1|^GPL-2\.0(-only)?$|^GPLv2$|GNU General Public License v2 \(GPLv2\)$|"
                  r"^JSON$|JSON License", re.I)
REVIEW = re.compile(r"AGPL|Affero|GPL-3|GPLv3|General Public License v3|GPL-2\.0-or-later|GPL-2\.0\+|GPLv2\+|"
                    r"or later \(GPLv2\+\)|LGPL|Lesser General|EPL-2\.0|Eclipse Public License 2", re.I)
ALLOW = re.compile(r"MIT|BSD|Apache|ISC|PSF|Python Software Foundation|Python-2\.0|MPL|Mozilla Public|"
                   r"Unlicense|Zlib|CC0|0BSD|BlueOak|HPND|Historical Permission|CC-BY-[34]\.0|Artistic-2\.0|"
                   r"BSL-1\.0|Boost Software|Public Domain|X11|PostgreSQL|OFL|Open Font|Unicode|W3C", re.I)

def term_class(term):
    t = term.strip().strip("()").strip()
    if not t or t.upper() in {"UNKNOWN", "NONE", "UNDEFINED"}:
        return "unknown"
    if t.upper() == "UNLICENSED" or DENY.search(t):
        return "denied"
    if REVIEW.search(t):
        return "review"
    if ALLOW.search(t):
        return "allowed"
    return "unknown"

RANK = {"allowed": 0, "review": 1, "unknown": 2, "denied": 3}

def classify(expr):
    alternatives = re.split(r"\s+OR\s+|;\s*|\s*/\s*(?=[A-Z])", expr)
    best = None
    for alt in alternatives:
        worst = max((term_class(t) for t in re.split(r"\s+AND\s+", alt)), key=RANK.get)
        best = worst if best is None or RANK[worst] < RANK[best] else best
    return best or "unknown"

result = {"allowed": [], "review": [], "unknown": [], "denied": []}
for row in rows:
    eco, name, lic = row["ecosystem"], row["name"], row.get("license") or ""
    if (eco, name.lower()) in SELF or (eco == "python" and name.lower() in TOOLING):
        continue
    lic = overrides.get((eco, name.lower()), lic)
    result[classify(lic)].append((eco, name, lic))
if len(sys.argv) > 3:
    expect = json.load(open(sys.argv[3]))
    got = {f"{e}:{n}": c for c, items in result.items() for e, n, _ in items}
    bad = {k: (v, got.get(k)) for k, v in expect.items() if got.get(k) != v}
    for k, (want, have) in bad.items():
        print(f"self-test FAILED: {k}: want {want}, got {have}")
    print("self-test ok" if not bad else "self-test FAILED")
    sys.exit(1 if bad else 0)
for cat, label in (("denied", "DENIED "), ("unknown", "UNKNOWN"), ("review", "REVIEW ")):
    for eco, name, lic in result[cat]:
        print(f"{label}  {eco}:{name}: {lic or '(no metadata)'}")
total = sum(len(v) for v in result.values())
print(f"licenses: {total} packages, {len(result['review'])} AGPL-compatible copyleft (review), "
      f"{len(result['unknown'])} unknown, {len(result['denied'])} denied")
sys.exit(1 if result["denied"] or result["unknown"] else 0)
PY
}

python_rows() {
  "${PIP_LICENSES:-pip-licenses}" --python "${TARGET_PYTHON:-python3}" --from=mixed --format=json > "$WORK/pip.json"
  "$PY" -c 'import json,sys; print(json.dumps([{"ecosystem":"python","name":r["Name"],"license":r.get("License","")} for r in json.load(open(sys.argv[1]))]))' "$WORK/pip.json"
}

node_rows() {
  (cd "$ROOT" && pnpm licenses list --json --prod) > "$WORK/pnpm.json"
  "$PY" -c 'import json,sys
data = json.load(open(sys.argv[1]))
rows = []
for lic, pkgs in data.items():
    for p in pkgs:
        rows.append({"ecosystem": "node", "name": p["name"], "license": lic})
print(json.dumps(rows))' "$WORK/pnpm.json"
}

self_test() {
  cat > "$WORK/rows.json" <<'JSON'
[{"ecosystem":"python","name":"fastapi","license":"MIT License"},
 {"ecosystem":"python","name":"psycopg","license":"GNU Lesser General Public License v3 (LGPLv3)"},
 {"ecosystem":"python","name":"certifi","license":"Mozilla Public License 2.0 (MPL 2.0)"},
 {"ecosystem":"python","name":"dual","license":"Apache Software License; BSD License"},
 {"ecosystem":"python","name":"gpl2only","license":"GPL-2.0-only"},
 {"ecosystem":"python","name":"gpl2plus","license":"GPL-2.0-or-later"},
 {"ecosystem":"python","name":"mystery","license":"UNKNOWN"},
 {"ecosystem":"python","name":"overridden","license":"UNKNOWN"},
 {"ecosystem":"python","name":"pip","license":"MIT"},
 {"ecosystem":"node","name":"next","license":"MIT"},
 {"ecosystem":"node","name":"choice","license":"(MIT OR GPL-3.0-or-later)"},
 {"ecosystem":"node","name":"both","license":"MIT AND CDDL-1.0"},
 {"ecosystem":"node","name":"closed","license":"UNLICENSED"},
 {"ecosystem":"node","name":"freebie","license":"Unlicense"},
 {"ecosystem":"node","name":"sspl","license":"SSPL-1.0"},
 {"ecosystem":"node","name":"agpl","license":"AGPL-3.0-only"},
 {"ecosystem":"node","name":"nc","license":"CC-BY-NC-4.0"},
 {"ecosystem":"node","name":"data","license":"CC-BY-4.0"}]
JSON
  cat > "$WORK/expect.json" <<'JSON'
{"python:fastapi":"allowed","python:psycopg":"review","python:certifi":"allowed","python:dual":"allowed",
 "python:gpl2only":"denied","python:gpl2plus":"review","python:mystery":"unknown","python:overridden":"allowed",
 "node:next":"allowed","node:choice":"allowed","node:both":"denied","node:closed":"denied",
 "node:freebie":"allowed","node:sspl":"denied","node:agpl":"review","node:nc":"denied","node:data":"allowed"}
JSON
  printf 'python overridden MIT  # verified upstream LICENSE file (self-test)\n' > "$WORK/overrides.txt"
  evaluate "$WORK/rows.json" "$WORK/overrides.txt" "$WORK/expect.json"
  printf 'python broken MIT\n' > "$WORK/bad-overrides.txt"
  if evaluate "$WORK/rows.json" "$WORK/bad-overrides.txt" >/dev/null 2>&1; then
    echo "self-test FAILED: an override without a source was accepted"; return 1
  fi
  echo "self-test ok: overrides need a source"
}

mode="${1:-all}"
case "$mode" in
  --self-test) self_test; exit $? ;;
  all|--python-only|--node-only) ;;
  *) echo "usage: $0 [--python-only|--node-only|--self-test]" >&2; exit 2 ;;
esac
overrides="$ROOT/scripts/license-overrides.txt"
[ -f "$overrides" ] || overrides="-"
echo "[]" > "$WORK/py-rows.json"; echo "[]" > "$WORK/node-rows.json"
if [ "$mode" != "--node-only" ]; then
  python_rows > "$WORK/py-rows.json"
fi
if [ "$mode" != "--python-only" ]; then
  if [ -f "$ROOT/apps/web/package.json" ]; then
    node_rows > "$WORK/node-rows.json"
  else
    echo "licenses: apps/web does not exist yet; Node licences skipped"
  fi
fi
"$PY" -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])) + json.load(open(sys.argv[2]))))' \
  "$WORK/py-rows.json" "$WORK/node-rows.json" > "$WORK/rows.json"
evaluate "$WORK/rows.json" "$overrides"
