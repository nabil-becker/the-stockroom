#!/usr/bin/env bash
# A consumer extends a shared skill without installing either layer as a Feature.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
src="$here/../../../src/component-registry"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp"/{bin,repo/.devcontainer,repo/shared,repo/project}
for cmd in dcf-registry registry-source-path; do
  install -m 755 "$src/$cmd.sh" "$tmp/bin/$cmd"
done
export PATH="$tmp/bin:$PATH" COMPONENT_REGISTRY_SHARE_DIR="$src" COMPONENT_REGISTRY_STATE_DIR="$tmp/state"
unset COMPONENT_REGISTRY_WHOAMI COMPONENT_REGISTRY_FILE COMPONENT_REGISTRY_WHOAMI_TASK_VAR COMPONENT_REGISTRY_FILE_TASK_VAR
cd "$tmp/repo"
cat > shared/review.layer <<'EOF'
[skills/review]
name:value = review
description:value = Review a change.
body:text = Check the public interface.
EOF
cat > project/review.layer <<'EOF'
[skills/review]
body:text = Check the published Feature ID.
EOF
cat > .devcontainer/registry.yml <<'EOF'
layers:
  - id: shared
    at: /
    required: true
    heading: false
    sources:
      - { kind: path, path: shared }
EOF
dcf-registry resolve --as /stockroom/clerk
skill="$tmp/state/view/skills/review/SKILL.md"
cat > "$tmp/expected" <<'EOF'
---
name: review
description: Review a change.
---

Check the public interface.
EOF
diff -u "$tmp/expected" "$skill"

cat >> .devcontainer/registry.yml <<'EOF'
  - id: project
    at: /
    required: true
    heading: false
    sources:
      - { kind: path, path: project }
EOF
dcf-registry resolve --as /stockroom/clerk
printf '\nCheck the published Feature ID.\n' >> "$tmp/expected"
diff -u "$tmp/expected" "$skill"
dcf-registry explain skills/review --color never > "$tmp/explanation"
grep -q 'shared@' "$tmp/explanation"
grep -q 'project@' "$tmp/explanation"
# shellcheck source=test/component-registry/unit/minijinja.sh
. "$here/minijinja.sh"
need_minijinja "$tmp/bin-render"
PATH="$tmp/bin-render:$PATH" dcf-registry render claude "$tmp/rendered"
diff -r "$tmp/state/view/skills" "$tmp/rendered/skills"
