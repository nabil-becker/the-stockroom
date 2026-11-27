#!/usr/bin/env bash
# Stage published Features from source so the lint toolchain exercises this checkout.
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf .devcontainer/features
mkdir -p .devcontainer/features
n=0
for d in src/*/; do
  [ -d "$d" ] || continue
  id="$(basename "$d")"
  if [ ! -f "$d/devcontainer-feature.json" ]; then
    echo "not staged: $d has no devcontainer-feature.json (a leftover directory? remove it)" >&2
    continue
  fi
  cp -r "$d" ".devcontainer/features/$id"
  n=$((n + 1))
done
echo "staged $n Features into .devcontainer/features"
