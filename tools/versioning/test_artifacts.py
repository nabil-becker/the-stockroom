import json
import tempfile
import unittest
from pathlib import Path

from artifacts import checked_history, inventory, prepare


class ArtifactVersions(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for name in ("one", "two"):
            folder = self.root / "devcontainer-features/src" / name
            folder.mkdir(parents=True)
            (folder / "devcontainer-feature.json").write_text('{\n  "version": "1.2.3"\n}\n')
            (folder / "CHANGELOG.md").write_text("# Changelog\n\n## [1.2.3]\n\nPrevious release.\n")
            records = self.root / "versions/devcontainer-features" / name / ".semversioner"
            records.mkdir(parents=True)
            (records / "1.2.3.json").write_text("[]\n")
        self.catalog = inventory(self.root)

    def history(self, name):
        key = f"devcontainer-features/{name}"
        return checked_history(self.root, key, self.catalog[key])

    def test_prepare_only_consumes_the_selected_artifacts_changes(self):
        one, two = self.history("one"), self.history("two")
        one.add_change("patch", "Fix a regression.")
        one.add_change("minor", "Add an option.")
        two.add_change("major", "Replace the interface.")
        selected = self.catalog["devcontainer-features/one"]
        self.assertEqual(prepare(one, selected), "1.3.0")
        self.assertEqual(json.loads(selected.source.read_text())["version"], "1.3.0")
        self.assertIn("Add an option.", selected.changelog.read_text())
        self.assertIn("Previous release.", selected.changelog.read_text())
        self.assertFalse(self.history("one").check())
        self.assertEqual(self.history("two").get_next_version(), "2.0.0")
        with self.assertRaisesRegex(ValueError, "no pending changes"):
            prepare(one, selected)

    def test_drift_is_refused_before_consuming_pending_changes(self):
        history = self.history("one")
        history.add_change("patch", "Fix the output.")
        self.catalog["devcontainer-features/one"].source.write_text('{\n  "version": "1.2.4"\n}\n')
        with self.assertRaisesRegex(ValueError, "history is 1.2.3"):
            self.history("one")
        self.assertTrue(history.check())

    def test_first_release_creates_the_feature_changelog(self):
        key = "devcontainer-features/one"
        source = self.catalog[key]
        baseline = self.root / "versions" / key / ".semversioner/1.2.3.json"
        baseline.rename(baseline.with_name("0.0.0.json"))
        source.source.write_text('{"version":"0.0.0"}')
        source.changelog.unlink()
        history = self.history("one")
        history.add_change("major", "First stable release.")
        self.assertEqual(prepare(history, source), "1.0.0")
        self.assertIn("- First stable release.", source.changelog.read_text())
        self.assertEqual(self.history("one").get_last_version(), "1.0.0")

    def test_misnamed_release_does_not_validate_by_filename_alone(self):
        record = self.root / "versions/devcontainer-features/one/.semversioner/1.2.3.json"
        record.write_text('{"version":"9.0.0","changes":[]}')
        with self.assertRaisesRegex(ValueError, "matching Semversioner release"):
            self.history("one")
