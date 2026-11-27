# the-stockroom

The stockroom packages artifacts for other repositories. The [Dev Container
Features](devcontainer-features/README.md) keep their existing
`ghcr.io/nabil-becker/devcontainer-features/<id>` references.

## Workstation environment

The dev container in `.devcontainer/` is infrastructure as code: every machine builds the same
environment from what is committed.

- `Dockerfile` pins the base image and the uv and ShellCheck images by tag and digest.
- `devcontainer.json` gives every Feature option that picks a tool version an exact value;
  `devcontainer-lock.json` pins each Feature's digest. The lint tools (ShellCheck, yamllint,
  PowerShell with Pester and PSScriptAnalyzer) match the collection's lint toolchain.
- `.python-version` and `uv.lock` pin Python (3.14, installed by uv) and the Python tools.
  Post-create runs `task env:setup`, which syncs `.venv` from `uv.lock`; run it again after
  pulling a `uv.lock` change.

`task env:check` verifies those pins. Inside the container it also reports a container built
from an older definition (run `task devcontainer:rebuild` on the host) and a `.venv` that no
longer matches `uv.lock`. The Workstation workflow rebuilds the container with
`--frozen-lockfile` for each change.

Dependabot proposes Feature, image, `uv.lock` and Actions updates weekly. Bump a Feature's tool
version by hand (for a shared lint tool, in `devcontainer-features/.devcontainer/` too). After
adding or removing a Feature, run `devcontainer build --workspace-folder .` to refresh the lock,
add the Feature to `VERSION_OPTIONS` in `tools/environment/check.py`, and commit the lock. Add a
Python tool with `uv add <package>==<version>` and commit `uv.lock`.

## Artifact versions

Each independently versioned artifact has a [Semversioner](https://github.com/raulgomis/semversioner)
history under `versions/<type>/<id>/.semversioner/`, outside the packaged files.
The imported baselines preserve the existing versions; earlier release notes stay in
the artifact changelogs. There is no stockroom-wide version.

The version tasks run the pinned Semversioner with `uv run --locked`, which syncs `.venv`
from `uv.lock` first. The dev container includes uv; elsewhere, install
[uv](https://docs.astral.sh/uv/) (it fetches the Python in `.python-version`).

From the repository root, record a changeset with the code it describes:

```sh
task version:change ARTIFACT=devcontainer-features/go-task TYPE=patch DESCRIPTION="Fix task discovery"
task version:status ARTIFACT=devcontainer-features/go-task
```

When preparing a release, run `task version:prepare ARTIFACT=devcontainer-features/go-task`.
Semversioner combines that artifact's pending changes, takes the highest bump, and the task
updates the packaging version and changelog. For Features, run `task devcontainer-features:docs`
and update any version assertions. Review and commit the changes. `task version:check` checks
for drift; **prepare never tags, pushes or publishes**.

Use `bundles/facilitator` for the application version shared by its tarballs and node image;
`devcontainer-features/facilitator` is the installer's separate version. A new bundle default
also needs a Feature changeset. For `components/participant`, run
`task devcontainer-features:components:sync` after preparing the component and record a change
for each Feature that vendors it.

Feature manifests and component `COMPONENT_VERSION` files are discovered automatically.
Seed `versions/<type>/<id>/.semversioner/<current-version>.json` with `[]` for an
existing artifact (an imported baseline, not a new release). For a new Feature, start
the manifest and baseline at `0.0.0`; prepare a `major` changeset for its first `1.0.0`.
For a new artifact type, add its native version field to `inventory()` in
`tools/versioning/artifacts.py`, include that file in the Artifact versions CI path
filter, and gate publication on `check --scope <type-or-key> --ready`.
