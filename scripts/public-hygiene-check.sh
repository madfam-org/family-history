#!/usr/bin/env bash
# Public-hygiene guard: this repository is public, so it must be publishable without a scrub
# (AGENTS.md, the repo-boundary contract). Scans every tracked text file and fails on:
#   private-ipv4     an RFC 1918 or RFC 6598 (carrier-grade NAT) address
#   cluster-dns      an in-cluster Service DNS name (the svc + cluster.local suffix) outside infra/
#   janua-client-id  a Janua OAuth client id literal (jnc_...)
#   vault-data-path  a Vault KV v2 API path (the mount, then the 'data' segment); manifests name secret/<project> only
#   node-hostname    something shaped like a cluster node or server hostname
# Exceptions live in scripts/public-hygiene-allowlist.txt, one per line, each with a reason:
#   <rule> <path-glob> <match-ERE>  # why this is public-safe
# The ERE is tested against the matched text only (not the whole line), and may not contain spaces.
#
# Usage: scripts/public-hygiene-check.sh [--root DIR] | --self-test
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
ROOT="$(cd "$(dirname "$SELF")/.." && pwd)"

rule_regex() {
  case "$1" in
    private-ipv4) printf '%s' '(^|[^0-9.])(10(\.[0-9]{1,3}){3}|172\.(1[6-9]|2[0-9]|3[01])(\.[0-9]{1,3}){2}|192\.168(\.[0-9]{1,3}){2}|100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])(\.[0-9]{1,3}){2})(/[0-9]{1,2})?' ;;
    cluster-dns) printf '%s' '[a-z0-9.-]*\.svc\.cluster\.local' ;;
    janua-client-id) printf '%s' 'jnc_[A-Za-z0-9_-]{8,}' ;;
    vault-data-path) printf '%s' 'secret/dat[a]/[A-Za-z0-9_./-]*' ;;
    node-hostname) printf '%s' '((k3s|k8s|kube)[-_]?(node|worker|master|server|agent|cp|control)[-_]?[0-9]+|(^|[^a-z0-9-])(node|worker|master)[-_][0-9]{1,3}($|[^0-9a-z])|your-server\.de|(^|[^a-z0-9])ip-[0-9]{1,3}(-[0-9]{1,3}){3})' ;;
  esac
}
RULES="private-ipv4 cluster-dns janua-client-id vault-data-path node-hostname"

scan() {
  local root="$1" allowlist="$1/scripts/public-hygiene-allowlist.txt" fail=0 hits=0
  local -a entries=()
  if [ -f "$allowlist" ]; then
    local n=0 line body why
    while IFS= read -r line || [ -n "$line" ]; do
      n=$((n + 1))
      case "$line" in ''|'#'*) continue ;; esac
      body="${line%%#*}"; why="${line#*#}"
      # shellcheck disable=SC2086
      set -- $body
      if [ "$#" -ne 3 ] || [ "$why" = "$line" ] || [ -z "${why// /}" ]; then
        echo "public-hygiene: allowlist line $n must be '<rule> <path-glob> <match-ERE>  # reason'" >&2
        fail=1; continue
      fi
      entries+=("$1 $2 $3")
    done < "$allowlist"
  fi

  local files
  files="$(cd "$root" && git ls-files | grep -v -E '^(LICENSE|NOTICE)$' || true)"
  [ -n "$files" ] || { echo "public-hygiene: no tracked files under $root" >&2; return 1; }

  local rule re hit path rest match entry e_rule e_glob e_re allowed
  for rule in $RULES; do
    re="$(rule_regex "$rule")"
    while IFS= read -r hit; do
      [ -n "$hit" ] || continue
      path="${hit%%:*}"; rest="${hit#*:}"; match="${rest#*:}"
      # Drop the one boundary character some rules capture in front of the value.
      if [[ "$match" =~ ^[^A-Za-z0-9] ]]; then match="${match:1}"; fi
      if [ "$rule" = cluster-dns ] && [[ "$path" == infra/* ]]; then continue; fi
      allowed=0
      for entry in ${entries[@]+"${entries[@]}"}; do
        read -r e_rule e_glob e_re <<<"$entry"
        # shellcheck disable=SC2053
        if [ "$e_rule" = "$rule" ] && [[ "$path" == $e_glob ]] && printf '%s' "$match" | grep -qiE -- "$e_re"; then
          allowed=1; break
        fi
      done
      if [ "$allowed" -eq 0 ]; then
        echo "public-hygiene: $rule: ${path}:${rest%%:*}" >&2
        hits=$((hits + 1))
      fi
    done < <(cd "$root" && printf '%s\n' "$files" | tr '\n' '\0' | xargs -0 grep -noHIiE -- "$re" 2>/dev/null || true)
  done
  if [ "$hits" -gt 0 ]; then
    echo "public-hygiene: $hits finding(s) (locations above; values not echoed). Remove them, or allowlist with a reason." >&2
    fail=1
  fi
  [ "$fail" -eq 0 ] && echo "public-hygiene: clean ($(printf '%s\n' "$files" | wc -l | tr -d ' ') tracked files)"
  return "$fail"
}

self_test() {
  local tmp out status=0
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' RETURN
  mkdir -p "$tmp/scripts" "$tmp/infra" "$tmp/docs"
  git -C "$tmp" init -q
  expect() { # expect <0|1> <label> [fragment]
    local want="$1" label="$2" frag="${3:-}" got=0
    git -C "$tmp" add -A >/dev/null
    out="$(scan "$tmp" 2>&1)" || got=1
    if [ "$got" -ne "$want" ] || { [ -n "$frag" ] && ! grep -q -- "$frag" <<<"$out"; }; then
      echo "self-test FAILED: $label (exit $got, want $want)"; echo "$out"; status=1
    else
      echo "self-test ok: $label"
    fi
  }
  printf 'hello\n' > "$tmp/README.md"
  expect 0 "clean tree passes"
  printf 'db at %s\n' "10.$((40 + 2)).0.7" > "$tmp/docs/a.md"
  expect 1 "private IPv4 fails" "private-ipv4: docs/a.md:1"
  printf 'egress except %s\n' "$(printf '10.%s.0.0/8' 0)" > "$tmp/docs/a.md"
  printf 'private-ipv4 docs/a.md ^10\\.0\\.0\\.0/8$  # generic CIDR constant\n' > "$tmp/scripts/public-hygiene-allowlist.txt"
  expect 0 "allowlisted CIDR passes"
  printf 'private-ipv4 docs/a.md ^10\\.0\\.0\\.0/8$\n' > "$tmp/scripts/public-hygiene-allowlist.txt"
  expect 1 "allowlist entry without a reason fails" "must be"
  : > "$tmp/scripts/public-hygiene-allowlist.txt"; rm "$tmp/docs/a.md"
  printf 'url: http://api.ns.svc.%s\n' "cluster.local" > "$tmp/infra/ok.yaml"
  expect 0 "cluster DNS inside infra/ passes"
  printf 'see http://api.ns.svc.%s\n' "cluster.local" > "$tmp/docs/b.md"
  expect 1 "cluster DNS outside infra/ fails" "cluster-dns"
  rm "$tmp/docs/b.md"
  printf 'id: %s\n' "jnc_$(printf 'Ab12Cd34Ef')" > "$tmp/docs/c.md"
  expect 1 "client id literal fails" "janua-client-id"
  printf 'path: secret/%s/app\n' "data" > "$tmp/docs/c.md"
  expect 1 "vault data path fails" "vault-data-path"
  printf 'host %s\n' "k3s-worker-$((1 + 1))" > "$tmp/docs/c.md"
  expect 1 "node hostname fails" "node-hostname"
  printf 'version 1.10.3 and node-ish words like nodes and node_modules\n' > "$tmp/docs/c.md"
  expect 0 "ordinary text passes"
  return "$status"
}

case "${1:-}" in
  --self-test) self_test ;;
  --root) scan "$(cd "$2" && pwd)" ;;
  "") scan "$ROOT" ;;
  *) echo "usage: $0 [--root DIR] | --self-test" >&2; exit 2 ;;
esac
