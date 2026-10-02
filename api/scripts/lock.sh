#!/usr/bin/env bash
# Regenerate the hashed requirement locks from pyproject.toml.
#
#   api/requirements/runtime.txt  what the image installs (pip --require-hashes)
#   api/requirements/dev.txt      runtime plus the dev extra (tests, lint, types)
#
# Universal resolution for Python 3.12, so one lock serves macOS laptops and linux/amd64 and
# linux/arm64 images. Run after any dependency change in pyproject.toml and commit the result.
set -euo pipefail

cd "$(dirname "$0")/.."

common=(
  --universal
  --python-version 3.12
  --generate-hashes
  --no-strip-extras
  --custom-compile-command "api/scripts/lock.sh"
)

echo "locking runtime dependencies"
uv pip compile --quiet pyproject.toml "${common[@]}" --output-file requirements/runtime.txt
echo "locking dev dependencies"
uv pip compile --quiet pyproject.toml "${common[@]}" --extra dev --output-file requirements/dev.txt
echo "done"
