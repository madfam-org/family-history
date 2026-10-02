#!/usr/bin/env bash
# Smoke an image under the production pod's restrictions (docs/ARCHITECTURE.md, Contracts): uid 1001,
# every capability dropped, no new privileges, read-only root filesystem, a tmpfs /tmp. Asserts the image's
# own USER is not root, then that the health endpoint answers 200 (and, optionally, that its body contains
# a fragment) within 90 seconds. On failure it prints the container's logs.
#
# Usage: scripts/ci/smoke-image.sh <image> <container-port> <health-path> <body-fragment|''> [docker run args...]
#        scripts/ci/smoke-image.sh --self-test
set -euo pipefail

is_root_user() { # the image's Config.User: empty, root, 0 or 0:<gid> all mean root
  case "$1" in ''|root|0|root:*|0:*) return 0 ;; *) return 1 ;; esac
}

self_test() {
  local fail=0 u
  for u in '' root 0 0:0 root:root; do
    is_root_user "$u" || { echo "self-test FAILED: '$u' should count as root"; fail=1; }
  done
  for u in 1001 1001:1001 node nextjs app; do
    if is_root_user "$u"; then echo "self-test FAILED: '$u' should not count as root"; fail=1; fi
  done
  if bash "${BASH_SOURCE[0]}" only-one-arg >/dev/null 2>&1; then echo "self-test FAILED: bad usage accepted"; fail=1; fi
  [ "$fail" -eq 0 ] && echo "self-test ok: smoke-image"
  return "$fail"
}

if [ "${1:-}" = "--self-test" ]; then self_test; exit $?; fi
if [ "$#" -lt 4 ]; then
  echo "usage: $0 <image> <container-port> <health-path> <body-fragment|''> [docker run args...]" >&2
  exit 2
fi
image="$1" port="$2" path="$3" fragment="$4"
shift 4

user="$(docker image inspect -f '{{.Config.User}}' "$image")"
if is_root_user "$user"; then
  echo "smoke: $image runs as root by default (USER '${user}'); the image must set a non-root USER" >&2
  exit 1
fi

name="smoke-$(basename "${image%%:*}")-$$"
host_port=$((20000 + RANDOM % 20000))
trap 'docker rm -f "$name" >/dev/null 2>&1 || true' EXIT

docker run -d --name "$name" \
  --user 1001:1001 --cap-drop ALL --security-opt no-new-privileges \
  --read-only --tmpfs /tmp \
  -p "127.0.0.1:${host_port}:${port}" "$@" "$image" >/dev/null

body=""
for _ in $(seq 1 45); do
  if body="$(curl -fsS --max-time 3 "http://127.0.0.1:${host_port}${path}" 2>/dev/null)"; then
    if [ -z "$fragment" ] || grep -qF -- "$fragment" <<<"$body"; then
      echo "smoke: $image answered ${path} under the restricted runtime: ${body:0:200}"
      exit 0
    fi
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" != "true" ]; then
    echo "smoke: $image exited before answering ${path}" >&2
    break
  fi
  sleep 2
done
echo "smoke: $image did not answer ${path} with 200${fragment:+ containing $fragment} (last body: ${body:0:200})" >&2
docker logs --tail 100 "$name" >&2 || true
exit 1
