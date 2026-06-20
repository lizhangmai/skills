#!/usr/bin/env python
"""Record monata-env setup commands, artifacts, and verification payloads."""

import argparse
import json
from pathlib import Path


ARTIFACT_PATTERNS = ("{package}-*.conda", "{package}-*.tar.bz2")


def parse_key_path(value):
    if "=" not in value:
        raise SystemExit(f"Expected key=path syntax: {value}")
    key, path = value.split("=", 1)
    key = key.strip()
    if not key:
        raise SystemExit(f"Key cannot be empty: {value}")
    return key, Path(path).expanduser().resolve()


def load_manifest(path):
    if not path.exists():
        raise SystemExit(f"Manifest does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Manifest is not valid JSON: {path}: {exc}") from exc
    data.setdefault("schema_version", 1)
    data.setdefault("plan", {})
    data.setdefault("execution", {})
    data["execution"].setdefault("commands_run", [])
    data["execution"].setdefault("artifacts", [])
    data.setdefault("verification", {})
    return data


def read_json_file(path):
    if not path.exists():
        return None, {
            "ok": False,
            "reason": "payload-missing",
            "path": str(path),
        }
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, {
            "ok": False,
            "reason": "invalid-json",
            "path": str(path),
            "error": str(exc),
        }


def append_command(data, args):
    if not any((args.command_kind, args.command, args.returncode is not None, args.stdout_file, args.stderr_file)):
        return
    missing = []
    if not args.command_kind:
        missing.append("--command-kind")
    if not args.command:
        missing.append("--command")
    if args.returncode is None:
        missing.append("--returncode")
    if missing:
        raise SystemExit("Command records require " + ", ".join(missing))

    record = {
        "kind": args.command_kind,
        "command": args.command,
        "returncode": args.returncode,
    }
    if args.stdout_file:
        record["stdout_file"] = str(args.stdout_file.expanduser().resolve())
    if args.stderr_file:
        record["stderr_file"] = str(args.stderr_file.expanduser().resolve())
    data["execution"]["commands_run"].append(record)


def update_verification(data, verification_values):
    errors = []
    for value in verification_values:
        key, path = parse_key_path(value)
        payload, error = read_json_file(path)
        if error is None:
            data["verification"][key] = payload
        else:
            data["verification"][key] = error
            errors.append(f"{key}: {error['reason']}: {path}")
    return errors


def collect_artifacts(data, artifact_dirs, packages):
    if not artifact_dirs or not packages:
        return

    existing = {item.get("path") for item in data["execution"]["artifacts"]}
    new_items = []
    for artifact_dir in artifact_dirs:
        root = artifact_dir.expanduser().resolve()
        if not root.exists():
            continue
        for package in packages:
            for pattern_template in ARTIFACT_PATTERNS:
                pattern = pattern_template.format(package=package)
                for path in sorted(root.rglob(pattern)):
                    if not path.is_file():
                        continue
                    resolved = str(path.resolve())
                    if resolved in existing:
                        continue
                    item = {
                        "package": package,
                        "path": resolved,
                        "filename": path.name,
                        "size": path.stat().st_size,
                    }
                    existing.add(resolved)
                    new_items.append(item)
    data["execution"]["artifacts"].extend(new_items)


def write_manifest(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="monata-env install manifest to update.")
    parser.add_argument("--command-kind", help="Logical command kind, such as build, install, smoke, or upstream.")
    parser.add_argument("--command", help="Exact command that was run.")
    parser.add_argument("--returncode", type=int, help="Command return code.")
    parser.add_argument("--stdout-file", type=Path, help="Path to the command stdout log or JSON file.")
    parser.add_argument("--stderr-file", type=Path, help="Path to the command stderr log.")
    parser.add_argument("--verification", action="append", default=[], help="Verification payload as key=json-file.")
    parser.add_argument("--artifact-dir", type=Path, action="append", default=[], help="Directory to scan for package artifacts.")
    parser.add_argument("--package", action="append", default=[], help="Package name whose artifacts should be recorded.")
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    return parser.parse_args()


def main():
    args = parse_args()
    manifest_path = args.manifest.expanduser().resolve()
    data = load_manifest(manifest_path)
    append_command(data, args)
    verification_errors = update_verification(data, args.verification)
    collect_artifacts(data, args.artifact_dir, args.package)
    write_manifest(manifest_path, data)

    summary = {
        "manifest": str(manifest_path),
        "commands_run": len(data["execution"]["commands_run"]),
        "artifacts": len(data["execution"]["artifacts"]),
        "verification": sorted(key for key, value in data["verification"].items() if value is not None),
    }
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"manifest: {summary['manifest']}")
        print(f"commands_run: {summary['commands_run']}")
        print(f"artifacts: {summary['artifacts']}")
        print("verification: " + (" ".join(summary["verification"]) if summary["verification"] else "none"))
    if verification_errors:
        for error in verification_errors:
            print(f"verification_error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
