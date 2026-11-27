"""Bridge independent Semversioner histories to the files the stockroom actually ships."""
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from semversioner.core import Semversioner


ROOT = Path(__file__).resolve().parents[2]
SEMVER = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"


@dataclass(frozen=True)
class Artifact:
    source: Path
    field: str
    changelog: Path | None = None

    def version_field(self) -> tuple[str, re.Match]:
        text = self.source.read_text(encoding="utf-8")
        match = re.search(self.field, text, re.M)
        if not match or (self.source.suffix == ".json" and json.loads(text)["version"] != match[1]):
            raise ValueError(f"{self.source}: cannot locate the packaging version")
        return text, match


def inventory(root: Path) -> dict[str, Artifact]:
    collection = root / "devcontainer-features"
    artifacts = {
        f"devcontainer-features/{p.parent.name}": Artifact(
            p, rf'"version"\s*:\s*"({SEMVER})"', p.with_name("CHANGELOG.md")
        )
        for p in (collection / "src").glob("*/devcontainer-feature.json")
    }
    for p in (collection / "components").glob("*/COMPONENT_VERSION"):
        artifacts[f"components/{p.parent.name}"] = Artifact(p, rf"^({SEMVER})$", p.with_name("CHANGELOG.md"))
    # The two bundle architectures and the node image all use the application version.
    artifacts["bundles/facilitator"] = Artifact(
        collection / "src/facilitator/facilitator/__init__.py", rf'^__version__ = "({SEMVER})"$'
    )
    return artifacts


def checked_history(root: Path, key: str, artifact: Artifact) -> Semversioner:
    base = root / "versions" / key
    records = list((base / ".semversioner").glob("*.json"))
    if not records:
        raise ValueError(f"{key}: missing Semversioner baseline under {base}")
    for record in records:
        if not re.fullmatch(SEMVER, record.stem):
            raise ValueError(f"{key}: invalid release filename {record.name}")
        data = json.loads(record.read_text(encoding="utf-8"))
        if data != [] and not (isinstance(data, dict) and data.get("version") == record.stem
                               and isinstance(data.get("changes"), list)):
            raise ValueError(f"{record}: expected an imported baseline or a matching Semversioner release")
    history = Semversioner(path=base)
    current = history.get_last_version()
    _, field = artifact.version_field()
    if current != field[1]:
        raise ValueError(f"{key}: history is {current}, but {artifact.source.name} declares {field[1]}")
    for change in history.fs.list_changesets():
        if change.type not in ("major", "minor", "patch") or not change.description.strip():
            raise ValueError(f"{key}: invalid pending changeset: {change}")
    return history


def prepare(history: Semversioner, artifact: Artifact) -> str:
    if not history.check():
        raise ValueError("no pending changes for this artifact")
    text, field = artifact.version_field()
    if artifact.changelog:
        if not artifact.changelog.exists() and field[1] == "0.0.0":
            log, pos = "# Changelog\n\n", len("# Changelog\n\n")
        else:
            log = artifact.changelog.read_text(encoding="utf-8")
            previous = re.search(r"^## \[", log, re.M)
            if not previous:
                raise ValueError(f"{artifact.changelog}: missing version heading")
            pos = previous.start()
    release = history.release()
    updated = text[:field.start(1)] + release.version + text[field.end(1):]
    artifact.source.write_text(updated, encoding="utf-8")
    if artifact.changelog:
        entry = f"## [{release.version}] - {release.created_at.date()}\n\n"
        entry += "".join(f"- {change.description}\n" for change in release.changes)
        artifact.changelog.write_text(log[:pos] + entry + "\n" + log[pos:], encoding="utf-8")
    return release.version


def main() -> None:
    catalog = inventory(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("change", "status", "prepare"):
        cmd = commands.add_parser(name)
        cmd.add_argument("artifact", choices=sorted(catalog))
        if name == "change":
            cmd.add_argument("type", choices=["major", "minor", "patch"])
            cmd.add_argument("description")
    check = commands.add_parser("check")
    check.add_argument("--scope", help="One artifact key or artifact type (default: all)")
    check.add_argument("--ready", action="store_true", help="Also refuse publication with pending changes")
    args = parser.parse_args()
    if args.command == "check":
        keys = [k for k in catalog if not args.scope or k == args.scope or k.split("/")[0] == args.scope]
        if not keys:
            parser.error(f"unknown artifact scope: {args.scope}")
        for key in sorted(keys):
            history = checked_history(ROOT, key, catalog[key])
            if args.ready and history.check():
                raise ValueError(f"{key}: pending changes; prepare and review this version before publishing")
        print(f"{len(keys)} artifact version(s) match Semversioner")
        return
    artifact = catalog[args.artifact]
    history = checked_history(ROOT, args.artifact, artifact)
    if args.command == "change":
        if not args.description.strip():
            parser.error("description must not be blank")
        print(history.add_change(args.type, args.description))
    elif args.command == "prepare":
        print(f"{args.artifact}: prepared {prepare(history, artifact)} (not published)")
    else:
        status = history.get_status()
        print(f"{args.artifact}: {status.version}" + (f" -> {status.next_version}" if status.next_version else ""))
        for change in status.unreleased_changes:
            print(f"  {change.type}: {change.description}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(str(error))
