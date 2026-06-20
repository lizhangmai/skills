#!/usr/bin/env python
"""Run a skill test command inside an isolated Singularity container."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SINGULARITY_BIN = "/opt/singularity-ce/4.1.1/bin/singularity"
DEFAULT_IMAGE = "docker://python:3.12-slim"
PREFLIGHT_SCRIPT = (
    "for command_name in \"$@\"; do "
    "command -v \"$command_name\" >/dev/null 2>&1 || printf '%s\\n' \"$command_name\"; "
    "done"
)


def resolve_path(path):
    return Path(path).expanduser().resolve()


def prepare_dirs(state_dir, channel_dir):
    state = resolve_path(state_dir)
    home = state / "home"
    cache = home / ".cache"
    channel = resolve_path(channel_dir) if channel_dir else state / "channel"
    singularity_cache = state / "singularity-cache"
    singularity_tmp = state / "singularity-tmp"
    for path in (home, cache, cache / "rattler", channel, singularity_cache, singularity_tmp):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "state_dir": state,
        "home_dir": home,
        "cache_dir": cache,
        "channel_dir": channel,
        "singularity_cache_dir": singularity_cache,
        "singularity_tmp_dir": singularity_tmp,
    }


def host_env(dirs):
    return {
        "SINGULARITY_CACHEDIR": str(dirs["singularity_cache_dir"]),
        "SINGULARITY_TMPDIR": str(dirs["singularity_tmp_dir"]),
    }


def build_command(args, dirs, command=None):
    workspace = resolve_path(args.workspace)
    repo_root = resolve_path(args.repo_root)
    container_command = args.command if command is None else command
    return [
        str(args.singularity_bin),
        "exec",
        "--cleanenv",
        "--containall",
        "--home",
        f"{dirs['home_dir']}:/tmp/skill-home",
        "--bind",
        f"{repo_root}:/mnt/skills:ro",
        "--bind",
        f"{workspace}:/mnt/project",
        "--bind",
        f"{dirs['channel_dir']}:/tmp/skill-channel",
        str(args.image),
        "env",
        "HOME=/tmp/skill-home",
        "PIXI_HOME=/tmp/skill-home/.pixi",
        "XDG_CACHE_HOME=/tmp/skill-home/.cache",
        "RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler",
        "CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel",
        *[str(part) for part in container_command],
    ]


def build_preflight_command(args, dirs):
    if not args.require_command:
        return []
    return build_command(args, dirs, ["sh", "-lc", PREFLIGHT_SCRIPT, "preflight", *args.require_command])


def preflight_next_actions(text):
    lower = text.lower()
    registry_tokens = (
        "docker://",
        "index.docker.io",
        "failed to get checksum",
        "could not resolve host",
        "connection timed out",
        "failed to download",
        "unable to handle",
        "network",
        "eof",
    )
    if any(token in lower for token in registry_tokens):
        return [
            {
                "id": "use-local-container-image",
                "title": "Use a local Singularity image",
                "requires_user_input": True,
                "command": "python scripts/skill_container.py --image /path/to/monata-env-test.sif ...",
                "prompt": "The container image could not be pulled or resolved from the registry. Ask the user for a local .sif image path, retry with a reachable image mirror, or reuse a state directory whose Singularity cache already contains the image.",
            }
        ]
    return []


def run_preflight(args, dirs):
    command = build_preflight_command(args, dirs)
    if not command:
        return 0
    env = os.environ.copy()
    env.update(host_env(dirs))
    result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        next_actions = preflight_next_actions(result.stdout + "\n" + result.stderr)
        payload = {
            "ok": False,
            "reason": "preflight-command-failed",
            "returncode": result.returncode,
            "required_commands": args.require_command,
            "image": str(args.image),
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
        if next_actions:
            payload["next_actions"] = next_actions
        print(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            )
        )
        return result.returncode

    missing = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if missing:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "missing-required-commands",
                    "missing": missing,
                    "required_commands": args.require_command,
                    "image": str(args.image),
                    "next_actions": [
                        {
                            "id": "choose-container-with-required-commands",
                            "title": "Use a container image with the required commands",
                            "requires_user_input": True,
                            "command": "python scripts/skill_container.py --image /path/to/image-with-tools.sif --require-command <command> ...",
                            "prompt": "The selected container image starts but does not contain the required command(s). Ask the user for an image or local .sif that already includes them, or choose a different image before running the live skill check.",
                        }
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 127
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--singularity-bin", default=DEFAULT_SINGULARITY_BIN)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--repo-root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--state-dir", type=Path, help="Host directory for isolated HOME/cache/channel state.")
    parser.add_argument("--channel", type=Path, help="Host directory bound to /tmp/skill-channel.")
    parser.add_argument("--dry-run", action="store_true", help="Print the container command as JSON without executing it.")
    parser.add_argument(
        "--require-command",
        action="append",
        default=[],
        help="Check that this command exists inside the container before running the requested command. Repeatable.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to run in the container, after --.")
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("provide a command after --")
    return args


def main():
    args = parse_args()
    state_dir = args.state_dir or Path(tempfile.mkdtemp(prefix="skill-container-"))
    dirs = prepare_dirs(state_dir, args.channel)
    command = build_command(args, dirs)
    preflight_command = build_preflight_command(args, dirs)
    summary = {
        "command": command,
        "preflight_command": preflight_command,
        "required_commands": args.require_command,
        "state_dir": str(dirs["state_dir"]),
        "home_dir": str(dirs["home_dir"]),
        "cache_dir": str(dirs["cache_dir"]),
        "channel_dir": str(dirs["channel_dir"]),
        "host_env": host_env(dirs),
        "repo_root": str(resolve_path(args.repo_root)),
        "workspace": str(resolve_path(args.workspace)),
        "image": str(args.image),
    }

    if args.dry_run:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    singularity_bin = Path(args.singularity_bin)
    if not singularity_bin.exists():
        print(f"ERROR: Singularity executable not found: {singularity_bin}", file=sys.stderr)
        return 2

    preflight_returncode = run_preflight(args, dirs)
    if preflight_returncode != 0:
        return preflight_returncode

    env = os.environ.copy()
    env.update(host_env(dirs))
    result = subprocess.run(command, env=env, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
