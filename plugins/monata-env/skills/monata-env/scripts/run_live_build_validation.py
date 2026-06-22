#!/usr/bin/env python
"""Run the highest-confidence isolated monata-env live build validation."""

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path

from plan_monata_env import create_plan, write_manifest_seed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Monata workspace to inspect.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Final local conda channel directory.")
    parser.add_argument("--session-dir", type=Path, required=True, help="Host directory for host-side plan artifacts.")
    parser.add_argument("--container-state-dir", type=Path, required=True, help="Host directory for isolated container state.")
    parser.add_argument("--local-source", action="append", default=[], help="Trusted local checkout as package=path.")
    parser.add_argument("--env-name", default="monata-env", help="pixi global environment name.")
    parser.add_argument("--conda-build-helper", type=Path, help="Path to conda-build helper rattler_channel.py.")
    parser.add_argument("--container-image", help="Singularity image URI or local .sif path for isolated live checks.")
    parser.add_argument("--host-pixi-root", type=Path, required=True, help="Host pixi installation root to bind read-only.")
    parser.add_argument("--upstream-profile", choices=("basic", "full"), default="basic")
    parser.add_argument("--live-timeout-seconds", type=int, help="Outer timeout for the generated container command.")
    parser.add_argument("--tool-pins-file", type=Path, help="Override the maintained circuit-tool pins JSON file.")
    parser.add_argument("--overwrite-manifest", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Plan and print the live command without running it.")
    parser.add_argument("--format", choices=("json", "summary"), default="json")
    return parser.parse_args(argv)


def live_artifacts(plan, output_dir, session_dir, container_state_dir):
    container_session_dir = Path(container_state_dir).resolve() / "home" / "monata-env-session"
    return {
        "host_manifest": str(Path(plan["manifest"]["path"]).resolve()),
        "host_session_dir": str(Path(session_dir).resolve()),
        "container_session_dir": str(container_session_dir),
        "container_manifest": str(container_session_dir / "monata-env-install-manifest.json"),
        "channel_dir": str(Path(output_dir).resolve()),
        "build_stdout": str(container_session_dir / "monata-env-build.out"),
        "build_stderr": str(container_session_dir / "monata-env-build.err"),
        "audit_json": str(container_session_dir / "monata-env-audit.json"),
    }


def print_result(result, output_format):
    if output_format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"ok: {result['ok']}")
    print(f"command_key: {result['command_key']}")
    print(f"command: {result['command']}")
    for key, value in result["artifacts"].items():
        print(f"{key}: {value}")


def main(argv=None):
    args = parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    session_dir = args.session_dir.expanduser().resolve()
    container_state_dir = args.container_state_dir.expanduser().resolve()
    plan = create_plan(
        root=args.root,
        output_dir=output_dir,
        local_source_values=args.local_source,
        env_name=args.env_name,
        conda_build_helper=args.conda_build_helper,
        container_image=args.container_image,
        session_dir=session_dir,
        container_state_dir=container_state_dir,
        upstream_profile=args.upstream_profile,
        host_pixi_root=args.host_pixi_root,
        live_timeout_seconds=args.live_timeout_seconds,
        tool_pins_file=args.tool_pins_file,
    )
    write_manifest_seed(plan, overwrite=args.overwrite_manifest)

    command = plan["container"]["live_build_install_smoke_upstream_command"]
    if not command:
        raise SystemExit(
            "Planner did not emit commands.build_install_smoke_upstream; provide local KLayout/Xschem sources, "
            "missing channel packages, and --host-pixi-root."
        )
    result = {
        "ok": True,
        "dry_run": args.dry_run,
        "command_key": "build_install_smoke_upstream",
        "command": command,
        "artifacts": live_artifacts(plan, output_dir, session_dir, container_state_dir),
        "plan": {
            "packages": plan["packages"],
            "build_packages": plan["build_packages"],
            "upstream_profile": plan["upstream_profile"],
            "tool_pins": plan["tool_pins"],
        },
    }
    if args.dry_run:
        print_result(result, args.format)
        return 0

    completed = subprocess.run(
        shlex.split(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    result["returncode"] = completed.returncode
    result["stdout"] = completed.stdout[-4000:]
    result["stderr"] = completed.stderr[-4000:]
    result["ok"] = completed.returncode == 0
    print_result(result, args.format)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
