#!/usr/bin/env python
"""Plan an AI-native monata-env setup session."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from detect_monata_tools import detect


SCRIPT_DIR = Path(__file__).resolve().parent
EXPECTED_SOURCE_REFS = {
    "klayout": "v0.30.9",
    "xschem": "3.4.7",
}
PIXI_PACKAGE_SPECS = {
    "ngspice": "ngspice=46.0",
    "openvaf-r": "openvaf-r",
    "klayout": "klayout=0.30.9",
    "xschem": "xschem=3.4.7",
}
EXPOSED_COMMANDS = {
    "ngspice": "ngspice",
    "openvaf-r": "openvaf-r",
    "klayout": "klayout",
    "xschem": "xschem",
}


def run_git(path, *args):
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def parse_key_path(values):
    parsed = {}
    for value in values or []:
        if "=" not in value:
            raise SystemExit(f"Expected package=path syntax: {value}")
        package, source = value.split("=", 1)
        package = package.strip()
        if not package:
            raise SystemExit(f"Package name cannot be empty: {value}")
        parsed[package] = Path(source).expanduser().resolve()
    return parsed


def local_source_status(package, path):
    target_ref = EXPECTED_SOURCE_REFS.get(package)
    item = {
        "path": str(path),
        "exists": path.exists(),
        "target_ref": target_ref,
        "status": "unchecked",
    }
    if not path.exists():
        item["status"] = "missing"
        return item
    inside = run_git(path, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        item["status"] = "not-git"
        return item
    head = run_git(path, "rev-parse", "HEAD")
    item["head"] = head
    if not target_ref:
        item["status"] = "ok"
        return item
    target = run_git(path, "rev-parse", "--verify", f"{target_ref}^{{commit}}")
    item["target_commit"] = target
    if not target:
        item["status"] = "target-ref-missing"
        return item
    if head == target:
        item["status"] = "ok"
    else:
        item["status"] = "ref-mismatch"
        item["recommended_worktree"] = f"/tmp/monata-sources/{package}-{target_ref}"
        item["worktree_command"] = [
            "git",
            "-C",
            str(path),
            "worktree",
            "add",
            "--detach",
            item["recommended_worktree"],
            target_ref,
        ]
    return item


def package_artifacts(output_dir, package):
    if output_dir is None or not output_dir.exists():
        return []
    patterns = [f"{package}-*.conda", f"{package}-*.tar.bz2"]
    artifacts = []
    for pattern in patterns:
        artifacts.extend(path for path in output_dir.rglob(pattern) if path.is_file())
    return sorted(str(path) for path in artifacts)


def channel_status(output_dir, packages):
    package_status = {}
    for package in packages:
        artifacts = package_artifacts(output_dir, package)
        package_status[package] = {
            "present": bool(artifacts),
            "artifacts": artifacts,
        }
    return {
        "output_dir": str(output_dir) if output_dir else "",
        "exists": bool(output_dir and output_dir.exists()),
        "packages": package_status,
        "missing": [package for package, item in package_status.items() if not item["present"]],
    }


def build_command(packages, output_dir, local_sources):
    command = [
        sys.executable,
        "scripts/rattler_channel.py",
        "build",
        "--recipe-set",
        "circuit-toolchain",
    ]
    for package in packages:
        command.extend(["--package", package])
    for package, path in local_sources.items():
        command.extend(["--local-source", f"{package}={path}"])
        if package in EXPECTED_SOURCE_REFS:
            command.extend(["--local-source-ref", f"{package}={EXPECTED_SOURCE_REFS[package]}"])
    command.append("--skip-existing")
    if output_dir:
        command.extend(["--output-dir", str(output_dir)])
    return command


def install_command(packages, output_dir, env_name):
    command = ["pixi", "global", "install", "--environment", env_name]
    if output_dir:
        command.extend(["--channel", output_dir.resolve().as_uri()])
    command.extend(["--channel", "conda-forge"])
    for package in packages:
        executable = EXPOSED_COMMANDS.get(package)
        if executable:
            command.extend(["--expose", f"{executable}={executable}"])
    for package in packages:
        command.append(PIXI_PACKAGE_SPECS.get(package, package))
    return command


def select_build_packages(packages, missing, local_sources):
    selected = set(missing) | set(local_sources)
    return [package for package in packages if package in selected]


def check_channel_command(packages, output_dir):
    command = [
        sys.executable,
        "scripts/rattler_channel.py",
        "check-channel",
        "--recipe-set",
        "circuit-toolchain",
    ]
    for package in packages:
        command.extend(["--package", package])
    if output_dir:
        command.extend(["--output-dir", str(output_dir)])
    return command


def upstream_installed_test_command(local_sources):
    command = [
        sys.executable,
        str(SCRIPT_DIR / "test_monata_env_upstream.py"),
        "--format",
        "json",
        "--profile",
        "basic",
    ]
    if "klayout" in local_sources:
        command.extend(["--klayout-source", str(local_sources["klayout"])])
    if "xschem" in local_sources:
        command.extend(["--xschem-source", str(local_sources["xschem"])])
    return command if len(command) > 6 else []


def test_profiles(local_sources):
    upstream_recommended = any(package in local_sources for package in ("klayout", "xschem"))
    return {
        "installed_smoke": {
            "recommended": True,
            "requires_local_source": False,
            "description": "Fast installed-tool smoke test that does not import Monata or use techlibs.",
        },
        "upstream_installed": {
            "recommended": upstream_recommended,
            "requires_local_source": True,
            "description": "Run safe upstream test subsets against installed tools when trusted local source checkouts are available.",
        },
        "upstream_full": {
            "recommended": False,
            "requires_local_source": True,
            "description": "Run broader upstream regression suites only when the user accepts longer runtime and extra dependencies.",
        },
    }


def questions(local_sources):
    items = []
    if any(item["status"] == "ref-mismatch" for item in local_sources.values()):
        items.append(
            {
                "id": "local_source_worktree",
                "question": "Local source checkout is not at the recipe ref. Create a temporary detached worktree instead of changing the user's checkout?",
                "recommended": True,
            }
        )
    if any(item["status"] in {"missing", "not-git", "target-ref-missing"} for item in local_sources.values()):
        items.append(
            {
                "id": "local_source_repair",
                "question": "One or more local sources cannot be validated. Ask the user for a corrected path, tag, or archive before building?",
                "recommended": True,
            }
        )
    return items


def create_plan(root, output_dir, local_source_values, env_name):
    detected = detect(root)
    packages = detected["packages"]
    local_source_paths = parse_key_path(local_source_values)
    local_sources = {
        package: local_source_status(package, path)
        for package, path in local_source_paths.items()
    }
    channel = channel_status(output_dir, packages)
    missing = channel["missing"]
    build_packages = select_build_packages(packages, missing, local_source_paths)
    selected_local_sources = {
        package: path
        for package, path in local_source_paths.items()
        if package in build_packages
    }
    tools = {
        package: {
            "command": EXPOSED_COMMANDS.get(package, package),
            "path": shutil.which(EXPOSED_COMMANDS.get(package, package)),
        }
        for package in packages
    }
    manifest_path = output_dir / "monata-env-install-manifest.json" if output_dir else Path("monata-env-install-manifest.json")
    return {
        "mode": "ai-native-session",
        "root": str(Path(root).resolve()),
        "env_name": env_name,
        "packages": packages,
        "detector": detected,
        "channel": channel,
        "local_sources": local_sources,
        "tools": tools,
        "questions": questions(local_sources),
        "commands": {
            "check_channel": check_channel_command(packages, output_dir),
            "build": build_command(build_packages, output_dir, selected_local_sources) if build_packages else [],
            "install": install_command(packages, output_dir, env_name),
            "smoke": [sys.executable, str(SCRIPT_DIR / "smoke_monata_env_tools.py"), "--format", "json"],
            "upstream_installed_tests": upstream_installed_test_command(local_source_paths),
        },
        "test_profiles": test_profiles(local_source_paths),
        "build_needed": bool(build_packages),
        "build_packages": build_packages,
        "manifest": {
            "path": str(manifest_path),
            "purpose": "Record choices, package artifacts, source refs, install command, and verification results.",
        },
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Monata workspace to inspect.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Final local conda channel directory.")
    parser.add_argument("--local-source", action="append", default=[], help="Trusted local checkout as package=path.")
    parser.add_argument("--env-name", default="monata-env", help="pixi global environment name.")
    parser.add_argument("--format", choices=("json", "summary"), default="json")
    parser.add_argument("--write-manifest", action="store_true", help="Write a manifest seed next to the output channel.")
    return parser.parse_args()


def print_summary(plan):
    print(f"mode: {plan['mode']}")
    print("packages: " + " ".join(plan["packages"]))
    missing = plan["channel"]["missing"]
    print("missing: " + (" ".join(missing) if missing else "none"))
    for question in plan["questions"]:
        print(f"question[{question['id']}]: {question['question']}")


def write_manifest_seed(plan):
    path = Path(plan["manifest"]["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "plan": plan,
        "execution": {
            "commands_run": [],
            "artifacts": [],
        },
        "verification": {
            "smoke": None,
            "upstream_installed": None,
        },
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    plan = create_plan(args.root, args.output_dir.resolve(), args.local_source, args.env_name)
    if args.write_manifest:
        write_manifest_seed(plan)
    if args.format == "summary":
        print_summary(plan)
    else:
        print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
