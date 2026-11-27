import json
import tempfile
import unittest
from pathlib import Path

from check import record, stale_errors, static_errors

DIGEST = "@sha256:" + "0" * 64
SHELLCHECK = f"FROM koalaman/shellcheck:v0.11.0{DIGEST} AS shellcheck\n"
COMMON = "ghcr.io/devcontainers/features/common-utils:2"
TASK = "ghcr.io/nabil-becker/devcontainer-features/go-task:1"
YAMLLINT = "ghcr.io/devcontainers-extra/features/yamllint:2"


class Environment(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.state = self.root / "state/environment.json"
        self.features = {
            COMMON: {"upgradePackages": False},
            TASK: {"version": "3.54.0"},
            YAMLLINT: {"version": "1.38.0"},
        }
        self.write_config()
        self.write(".devcontainer/Dockerfile", SHELLCHECK + f"FROM mcr.microsoft.com/devcontainers/base:2-bookworm{DIGEST}\n")
        self.write(".devcontainer/devcontainer-lock.json", json.dumps({"features": {ref: {} for ref in self.features}}))
        self.write("devcontainer-features/.devcontainer/Dockerfile",
                   SHELLCHECK + f"FROM mcr.microsoft.com/devcontainers/base:2-trixie{DIGEST}\n")
        self.write("devcontainer-features/.devcontainer/devcontainer.json",
                   json.dumps({"features": {YAMLLINT: {"version": "1.38.0"}}}))
        self.write(".python-version", "3.14\n")

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write_config(self, comment="the workstation"):
        body = json.dumps({"build": {"dockerfile": "Dockerfile"}, "features": self.features}, indent=2)
        self.write(".devcontainer/devcontainer.json", f"// {comment}\n{body[:-1]}  /* end */\n}}\n")

    def test_a_fully_pinned_definition_passes(self):
        self.assertEqual(static_errors(self.root), [])

    def test_floating_or_default_versions_and_unknown_features_are_flagged(self):
        self.features[TASK] = {"version": "latest"}
        self.features[COMMON] = {}
        self.features["ghcr.io/example/features/mystery:1"] = {}
        self.write_config()
        errors = "\n".join(static_errors(self.root))
        self.assertIn(f"{TASK}: set version to an exact version (or none), not 'latest'", errors)
        self.assertIn(f"{COMMON}: set upgradePackages to false", errors)
        self.assertIn("mystery:1: unknown to tools/environment/check.py", errors)
        del self.features[TASK]["version"]
        self.write_config()
        self.assertIn(f"{TASK}: set version to an exact version (or none), not its default",
                      static_errors(self.root))

    def test_images_must_be_pinned_by_digest_and_match_the_collections_tools(self):
        self.write(".devcontainer/Dockerfile",
                   "FROM koalaman/shellcheck:v0.10.0 AS shellcheck\nFROM mcr.microsoft.com/devcontainers/base:2-bookworm\n")
        errors = "\n".join(static_errors(self.root))
        self.assertIn("pin FROM koalaman/shellcheck:v0.10.0 to a tag and its digest", errors)
        self.assertIn("pin FROM mcr.microsoft.com/devcontainers/base:2-bookworm to a tag", errors)
        self.assertIn(f"use the collection lint Dockerfile's stage FROM koalaman/shellcheck:v0.11.0{DIGEST}", errors)

    def test_the_lock_must_match_the_features_used(self):
        self.write(".devcontainer/devcontainer-lock.json", json.dumps({"features": {
            COMMON: {"dependsOn": ["ghcr.io/example/features/dependency:1"]},
            TASK: {},
            "ghcr.io/example/features/dependency:1": {},
            "ghcr.io/example/features/removed:1": {},
        }}))
        self.assertEqual(static_errors(self.root), [
            f"{YAMLLINT} has no entry in .devcontainer/devcontainer-lock.json: build once "
            "(the devcontainer CLI writes the lock) and commit it",
            ".devcontainer/devcontainer-lock.json pins ghcr.io/example/features/removed:1, which devcontainer.json "
            "no longer uses: build once to refresh the lock",
        ])

    def test_the_collections_lint_options_must_match(self):
        self.features[YAMLLINT] = {"version": "1.37.0"}
        self.write_config()
        self.assertEqual(static_errors(self.root), [
            f"{YAMLLINT}: version is '1.37.0', the collection's lint toolchain pins '1.38.0' "
            "(devcontainer-features/.devcontainer/devcontainer.json): change both together",
        ])

    def test_the_record_is_kept_and_only_a_real_change_makes_the_container_stale(self):
        self.assertIn("run task env:setup", stale_errors(self.root, self.state)[0])
        self.assertIn("recorded", record(self.root, self.state))
        self.assertEqual(stale_errors(self.root, self.state), [])

        self.write_config(comment="reworded comment")
        self.write(".devcontainer/Dockerfile",
                   "# a note\n" + self.root.joinpath(".devcontainer/Dockerfile").read_text() + "\n")
        self.assertEqual(stale_errors(self.root, self.state), [])

        self.features[TASK] = {"version": "3.55.0"}
        self.write_config()
        self.assertIn("kept", record(self.root, self.state))
        self.assertEqual(stale_errors(self.root, self.state), [
            "this container was created from an older devcontainer.json: run task devcontainer:rebuild on the host",
        ])


if __name__ == "__main__":
    unittest.main()
