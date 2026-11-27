# Copilot instructions: the-stockroom

You are the **warehouse clerk**. This repo is a stockroom of artifacts that are packaged and released for consumption by *other* repos. It must support several artifact types side by side:

- Python packages
- PowerShell modules
- Devcontainer Features
- Docker images
- Helm charts
- Components referenced by the `component-registry` Feature from `nabil-becker/devcontainer-features` (resolved from a consumer's `.devcontainer/registry.yml` into skills/agents)

Keep each artifact type self-contained under its own top-level folder. Expose its tasks under a matching namespace in the root Taskfile; keep GitHub Actions workflows at the repository root.

## Layout

- `devcontainer-features/` was imported from `nabil-becker/devcontainer-features` at `9295031`. Only `src/<id>/` is packaged. `components/` supplies code vendored into Features; `bundles/` builds facilitator assets. Do not import upstream's local-only Features (including `devhost`).
- `test/<id>/` holds a Feature's defaults and scenarios; `test/_global/` installs them together. Root `.github/workflows/devcontainer-features-*.yaml` discover IDs from `src/`, not from test directories (which also contain support suites). Keep the all-Features scenario in sync when adding an ID.
- Keep `ghcr.io/nabil-becker/devcontainer-features/<id>` stable: the publisher needs **both** `base-path-to-features: ./devcontainer-features/src` and `features-namespace: nabil-becker/devcontainer-features`. Releases are manually started on `main`, not on push or PR. The [collection guide](../devcontainer-features/CONTRIBUTING.md) describes versioning, changelogs and the facilitator bundle/pin/image sequence.

## Commands

All tasks go through [go-task](https://taskfile.dev) (`Taskfile.yml`):

- `task` / `task --list`: list tasks.
- `task devcontainer-features:lint` runs the collection's linters, Pester, drift checks and Docker-free unit tests. `task devcontainer-features:test:registry-first-use` exercises one layered-registry consumer without Docker. The lint tools are pinned in the collection's devcontainer (`devcontainer-features/.devcontainer/`) and installed at the same versions in the root workstation container; `task env:check` enforces the match.
- `task env:setup` syncs `.venv` from `uv.lock` (post-create runs it). `task env:check` checks that the environment definition pins every version and, inside the container, that the container and `.venv` match it. Tests: `python3 -m unittest discover -s tools/environment`.
- `task devcontainer-features:test FEATURE=go-task` runs one Feature; omit `FEATURE` for the collection. `task devcontainer-features:test:global` runs the combined scenario. Use a Docker host that can mount the CLI's temporary workspace; these tasks must never prune the host daemon.
- `task devcontainer-features:docs` regenerates Feature READMEs from metadata, `NOTES.md` and changelogs; `task devcontainer-features:docs:check` detects drift. Run `task devcontainer-features:common:sync` or `:components:sync` after editing a shared helper or component.
- `task shutdown:check`: runs `.devcontainer/shutdown-check.sh` (refuses a stop with a git operation in progress or a leftover stash). Add repo-specific checks to that script.
- `task devcontainer:*` (alias `dc:`, e.g. `task dc:up`): host-side launcher, vendored from `nabil-becker/devcontainer-features` by `bootstrap.ps1`/`bootstrap.sh` into `.devcontainer/cli_bootstrap.ignore/`. That folder is git-ignored; on a fresh clone run the bootstrap one-liner first (the include is `optional: true`, so tasks silently vanish until then). Re-run the bootstrap to refresh it. Never edit or commit it.
- Feature-contributed tasks (`dsc:*`, `velero:*`, `agents:*`, `component-registry:*`, ...) are flattened in from `/usr/local/share/go-task/features.yml`, which exists only inside the container and is generated; do not edit it.
- `cloud-folder:*` and `audio:*` are included only on the host, not in the container.

When adding build/test/release tasks for an artifact type, add them to `Taskfile.yml` (namespaced per type, e.g. via `includes:`) rather than introducing another runner, and document how to run a single test there.

## Environment and configuration

- The workstation devcontainer is infrastructure as code, identical on every machine: `.devcontainer/Dockerfile` pins `mcr.microsoft.com/devcontainers/base:2-bookworm` and the tool images by digest; `.devcontainer/devcontainer.json` adds Features from `ghcr.io/nabil-becker/devcontainer-features/*` (go-task, git, claude-code, copilot, component-registry, openbao, sign-packet, facilitator, ...), PowerShell, Docker, Helm and yamllint with an exact version for every version option; `devcontainer-lock.json` pins Feature digests. Never introduce `latest` or an unpinned image; a new Feature needs a `VERSION_OPTIONS` entry in `tools/environment/check.py` and a refreshed lock.
- Python comes from uv (version in `.python-version`); Python tools are declared in `pyproject.toml` and locked in `uv.lock`. Run them with `uv run --locked`; add one with `uv add`. CI installs the uv version pinned in the Dockerfile via `.github/actions/setup-uv`. Dependabot updates Features, Dockerfile digests, `uv.lock` and Actions.
- Host-specific settings live in `.devcontainer/.env` (git-ignored; template: `.devcontainer/.env.example`) and are loaded by the root Taskfile `dotenv:`. Precedence: CLI var > `.env` > exported env var. Never put credentials there.
- `DCF_HOST_*` container env vars are set by the launcher (`task devcontainer:up`). Opening the folder directly in VS Code leaves them empty, so start via the tasks.
- Secrets go through `dcf-secret` (OpenBao Feature), not files in the repo.
- Changes to the Dockerfile, `runArgs` or Features take effect only after `task devcontainer:rebuild`; `task env:check` reports a container built from an older definition.

## Conventions

- Use the pinned Semversioner and `task version:change/status/prepare` (e.g. `task version:status ARTIFACT=devcontainer-features/go-task`), not a repository-wide tag or a hand-edited manifest version. Histories live outside packages under `versions/<type>/<id>/.semversioner/`. `task version:check` compares them to the native package versions. Preparing files for review and publishing are separate operations; see [Artifact versions](../README.md#artifact-versions).
- Repo-wide decisions elsewhere in this collection are recorded as ADRs (e.g. "ADR 0057", "ADR-0063" referenced in the Taskfile/devcontainer); follow them and reference ADR numbers rather than restating rationale.
- Cost matters to the owner: prefer cheap CI/runner choices, avoid unnecessary paid services or large image builds, and state spend uncertainty when proposing anything that incurs cost.
- The owner mostly works from a phone: keep PRs small, summaries short, and artifacts reviewable on mobile.
