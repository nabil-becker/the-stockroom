#!/usr/bin/env python3
"""Check that the workstation environment is one pinned definition, built the same everywhere.

check   The definition pins every version: FROM lines with a digest (the workstation's and the
        collection's lint Dockerfile), an exact value for each Feature option that picks a tool
        version, a lock entry for each Feature, the collection's lint toolchain at the same
        versions, a Python version, and uv.lock current with pyproject.toml. Inside the
        workstation container (STOCKROOM_WORKSTATION=1, set by its Dockerfile) also: the container
        was created from the current definition (else rebuild) and .venv matches uv.lock (else
        task env:setup).
record  Inside the workstation, write down the definition this container was created from. An
        existing record is kept, so only the first run after a (re)build, post-create's, writes.

Stdlib only: it runs before .venv exists, and on a host's python3 too.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKSTATION = Path(".devcontainer")
COLLECTION = Path("devcontainer-features/.devcontainer")
WORKFLOW = Path(".github/workflows/workstation.yaml")
FLOATING = {"", "latest", "stable", "lts", "current", "preview", "prerelease"}
# The options that pick a tool version, per Feature (reference without its tag); each must name an
# exact version (or "none"). A Feature missing here fails the check: add it, with () when no
# option picks a version (its digest in devcontainer-lock.json then fixes what it installs).
VERSION_OPTIONS = {
    "ghcr.io/devcontainers/features/common-utils": (),
    "ghcr.io/devcontainers/features/docker-outside-of-docker": ("version", "mobyBuildxVersion", "dockerDashComposeVersion"),
    "ghcr.io/devcontainers/features/kubectl-helm-minikube": ("version", "helm", "minikube"),
    "ghcr.io/devcontainers/features/powershell": ("version",),
    "ghcr.io/devcontainers-extra/features/yamllint": ("version",),
    "ghcr.io/nabil-becker/devcontainer-features/claude-code": ("version",),
    "ghcr.io/nabil-becker/devcontainer-features/component-registry": (),
    "ghcr.io/nabil-becker/devcontainer-features/copilot": (),
    "ghcr.io/nabil-becker/devcontainer-features/devcontainer-cli": ("version",),
    "ghcr.io/nabil-becker/devcontainer-features/facilitator": (),
    "ghcr.io/nabil-becker/devcontainer-features/git": (),
    "ghcr.io/nabil-becker/devcontainer-features/go-task": ("version",),
    "ghcr.io/nabil-becker/devcontainer-features/openbao": ("version",),
    "ghcr.io/nabil-becker/devcontainer-features/sign-packet": (),
    "ghcr.io/nabil-becker/devcontainer-features/ssh-agent": (),
}
# Options whose default makes the image depend on the day it was built.
REQUIRED = {"ghcr.io/devcontainers/features/common-utils": {"upgradePackages": False}}
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.S)
FROM = re.compile(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?\s*$", re.M | re.I)
PINNED = re.compile(r"^[^@\s]+:[^@\s/]+@sha256:[0-9a-f]{64}$")
CLI = re.compile(r"@devcontainers/cli@([^\s'\"]+)")


def load_jsonc(path: Path):
    text = TOKEN.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", path.read_text(encoding="utf-8"))
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def untagged(ref: str) -> str:
    """ghcr.io/owner/x:1 -> ghcr.io/owner/x (also for an image name before its digest)."""
    name = ref.split("@", 1)[0]
    head, sep, tag = name.rpartition(":")
    return head if sep and "/" not in tag else name


def feature_id(ref: str) -> str:
    return untagged(ref).rstrip("/").rsplit("/", 1)[-1]


def tool_images(dockerfile: Path, errors: list[str]) -> dict[str, str]:
    """Check that every FROM is pinned; return the named stages' images by repository."""
    label = dockerfile.as_posix()
    if not dockerfile.is_file():
        errors.append(f"{label} is missing")
        return {}
    stages: set[str] = set()
    tools: dict[str, str] = {}
    for image, stage in FROM.findall(dockerfile.read_text(encoding="utf-8")):
        if image.lower() != "scratch" and image not in stages and not PINNED.match(image):
            errors.append(f"{label}: pin FROM {image} to a tag and its digest (name:tag@sha256:...)")
        if stage:
            stages.add(stage)
            tools[untagged(image)] = image
    return tools


def static_errors(root: Path) -> list[str]:
    errors: list[str] = []
    workstation = root / WORKSTATION
    config = load_jsonc(workstation / "devcontainer.json")
    dockerfile = config.get("build", {}).get("dockerfile")
    if "image" in config or not dockerfile:
        errors.append(".devcontainer/devcontainer.json: build from a Dockerfile (build.dockerfile) instead of image, "
                      "so the base is pinned by digest where Dependabot updates it")
        tools = {}
    else:
        tools = tool_images(workstation / dockerfile, errors)
    for repository, image in tool_images(root / COLLECTION / "Dockerfile", errors).items():
        if tools.get(repository) != image:
            errors.append(f".devcontainer/{dockerfile}: use the collection lint Dockerfile's stage FROM {image}, "
                          f"not {tools.get(repository, 'none')}")

    features = config.get("features", {})
    for ref, options in features.items():
        name = untagged(ref)
        if name not in VERSION_OPTIONS:
            errors.append(f"{ref}: unknown to tools/environment/check.py; add it to VERSION_OPTIONS "
                          "with the options that pick its tool versions (() if none)")
            continue
        for option in VERSION_OPTIONS[name]:
            value = str(options.get(option, "")).strip()
            if value.lower() in FLOATING:
                found = repr(value) if value else "its default"
                errors.append(f"{ref}: set {option} to an exact version (or none), not {found}")
        for option, wanted in REQUIRED.get(name, {}).items():
            if options.get(option) != wanted:
                errors.append(f"{ref}: set {option} to {json.dumps(wanted)}")

    lock_path = workstation / "devcontainer-lock.json"
    locked = json.loads(lock_path.read_text(encoding="utf-8")).get("features", {}) if lock_path.is_file() else {}
    used = {ref for ref in features if not ref.startswith(".")}
    for ref in sorted(used - set(locked)):
        errors.append(f"{ref} has no entry in .devcontainer/devcontainer-lock.json: build once "
                      "(the devcontainer CLI writes the lock) and commit it")
    dependencies = {dep for entry in locked.values() for dep in entry.get("dependsOn", [])}
    for ref in sorted(set(locked) - used - dependencies):
        errors.append(f".devcontainer/devcontainer-lock.json pins {ref}, which devcontainer.json no longer uses: "
                      "build once to refresh the lock")

    own = {feature_id(ref): (ref, options) for ref, options in features.items()}
    lint = load_jsonc(root / COLLECTION / "devcontainer.json")
    for ref, options in lint.get("features", {}).items():
        if feature_id(ref) not in own:
            errors.append(f"the collection's lint toolchain installs {ref}: add it to .devcontainer/devcontainer.json "
                          "with the same options")
            continue
        mine, mine_options = own[feature_id(ref)]
        if not ref.startswith(".") and mine != ref:
            errors.append(f"{mine}: use {ref}, the reference the collection's lint toolchain uses")
        for option, value in options.items():
            if mine_options.get(option) != value:
                errors.append(f"{mine}: {option} is {mine_options.get(option)!r}, the collection's lint toolchain pins "
                              f"{value!r} (devcontainer-features/.devcontainer/devcontainer.json): change both together")

    workflow = root / WORKFLOW
    if workflow.is_file():
        cli = own.get("devcontainer-cli", (None, {}))[1].get("version")
        for version in sorted(set(CLI.findall(workflow.read_text(encoding="utf-8")))):
            if version != cli:
                errors.append(f"{WORKFLOW.as_posix()} builds with @devcontainers/cli@{version}; use the "
                              f"workstation's devcontainer-cli version, {cli}")

    python = root / ".python-version"
    if not python.is_file() or not re.fullmatch(r"3\.\d+(\.\d+)?", python.read_text(encoding="utf-8").strip()):
        errors.append(".python-version: name the Python version for .venv (3.X or 3.X.Y)")
    return errors


def definition(root: Path) -> dict[str, str]:
    """A digest of each file the image is built from; comments and layout do not count."""
    workstation = root / WORKSTATION
    dockerfile = load_jsonc(workstation / "devcontainer.json").get("build", {}).get("dockerfile", "Dockerfile")
    digests = {}
    for name in ("devcontainer.json", "devcontainer-lock.json", dockerfile):
        path = workstation / name
        if not path.is_file():
            digests[name] = "missing"
            continue
        if path.suffix == ".json":
            text = json.dumps(load_jsonc(path), sort_keys=True, separators=(",", ":"))
        else:
            lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
            text = "\n".join(line for line in lines if line and not line.startswith("#"))
        digests[name] = hashlib.sha256(text.encode()).hexdigest()
    return digests


def state_file() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state"
    return Path(base) / "stockroom" / "environment.json"


def record(root: Path, state: Path) -> str:
    if state.is_file():
        return f"kept the record of {json.loads(state.read_text()).get('created', 'an earlier start')} ({state})"
    state.parent.mkdir(parents=True, exist_ok=True)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.write_text(json.dumps({"created": created, "definition": definition(root)}, indent=2) + "\n")
    return f"recorded the definition this container was created from ({state})"


def stale_errors(root: Path, state: Path) -> list[str]:
    if not state.is_file():
        return ["no record of the definition this container was created from: run task env:setup (post-create runs it)"]
    recorded = json.loads(state.read_text()).get("definition", {})
    changed = [name for name, digest in definition(root).items() if recorded.get(name) != digest]
    if changed:
        return [f"this container was created from an older {', '.join(changed)}: "
                "run task devcontainer:rebuild on the host"]
    return []


def uv_errors(root: Path, workstation: bool) -> list[str]:
    uv = shutil.which("uv")
    if uv is None:
        if workstation:
            return ["uv is missing from this container: run task devcontainer:rebuild on the host"]
        print("environment: uv not found; skipped the uv.lock check")
        return []
    runs = [(["lock", "--check"], "uv.lock is out of date with pyproject.toml: run uv lock and commit uv.lock")]
    if workstation:
        runs.append((["sync", "--locked", "--check"], ".venv does not match uv.lock: run task env:setup"))
    errors = []
    for args, message in runs:
        done = subprocess.run([uv, *args], cwd=root, capture_output=True, text=True)
        if done.returncode:
            detail = (done.stderr or done.stdout).strip().splitlines()
            errors.append(message + (f" ({detail[-1]})" if detail else ""))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("check", "record"))
    args = parser.parse_args(argv)
    workstation = os.environ.get("STOCKROOM_WORKSTATION") == "1"
    if args.command == "record":
        print("environment: " + (record(ROOT, state_file()) if workstation
                                 else "not the workstation container; nothing to record"))
        return 0
    errors = static_errors(ROOT)
    if workstation:
        errors += stale_errors(ROOT, state_file())
    errors += uv_errors(ROOT, workstation)
    for error in errors:
        print(f"environment: {error}")
    if errors:
        return 1
    print("environment: every version is pinned"
          + ("; this container matches the definition and .venv matches uv.lock" if workstation else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
