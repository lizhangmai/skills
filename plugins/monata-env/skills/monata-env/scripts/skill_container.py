#!/usr/bin/env python
"""Run a skill test command inside an isolated Singularity container."""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SINGULARITY_BIN = "/opt/singularity-ce/4.1.1/bin/singularity"
DEFAULT_IMAGE = "docker://python:3.12-slim"
DEFAULT_CONTAINER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
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
    singularity_command = [
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
    ]
    for bind in args.bind:
        singularity_command.extend(["--bind", str(bind)])
    container_env = [
        "HOME=/tmp/skill-home",
        "PIXI_HOME=/tmp/skill-home/.pixi",
        "XDG_CACHE_HOME=/tmp/skill-home/.cache",
        "RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler",
        "CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel",
    ]
    if args.prepend_path:
        container_env.append("PATH=" + ":".join(args.prepend_path + [DEFAULT_CONTAINER_PATH]))
    return [
        *singularity_command,
        str(args.image),
        "env",
        *container_env,
        *[str(part) for part in container_command],
    ]


def build_preflight_command(args, dirs):
    if not args.require_command:
        return []
    return build_command(args, dirs, ["sh", "-c", PREFLIGHT_SCRIPT, "preflight", *args.require_command])


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


def preflight_error_code(reason, text):
    if preflight_next_actions(text):
        return "registry-download-failed"
    return reason


def decoded_output(value):
    if not value:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def positive_timeout_seconds(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("--timeout-seconds must be a positive integer")
    if number <= 0:
        raise argparse.ArgumentTypeError("--timeout-seconds must be a positive integer")
    return number


def container_timeout_payload(args, dirs, command, exc):
    timeout_seconds = args.timeout_seconds
    return {
        "ok": False,
        "reason": "container-command-timeout",
        "error": {"code": "container-command-timeout"},
        "returncode": 124,
        "timeout_seconds": timeout_seconds,
        "command": [str(part) for part in command],
        "image": str(args.image),
        "state_dir": str(dirs["state_dir"]),
        "home_dir": str(dirs["home_dir"]),
        "cache_dir": str(dirs["cache_dir"]),
        "channel_dir": str(dirs["channel_dir"]),
        "stdout": decoded_output(exc.stdout)[-4000:],
        "stderr": decoded_output(exc.stderr)[-4000:],
        "next_actions": [
            {
                "id": "inspect-container-timeout-or-cache",
                "title": "Inspect the timed-out live container run",
                "requires_user_input": True,
                "prompt": (
                    "The isolated live validation command exceeded its outer timeout. "
                    "Inspect the persisted state/cache/channel directories, check whether the build is still "
                    "downloading or compiling large dependencies, then retry with a larger --timeout-seconds, "
                    "a warmer cache, or narrower runbook steps."
                ),
            }
        ],
    }


def terminate_process_group(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    process.wait()


def run_captured_command(command, env, timeout=None):
    process = subprocess.Popen(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        terminate_process_group(process)
        stdout, stderr = process.communicate()
        exc.stdout = stdout
        exc.stderr = stderr
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout=stdout, stderr=stderr)


def run_preflight(args, dirs):
    command = build_preflight_command(args, dirs)
    if not command:
        return 0
    env = os.environ.copy()
    env.update(host_env(dirs))
    try:
        result = run_captured_command(command, env=env, timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        print(json.dumps(container_timeout_payload(args, dirs, command, exc), indent=2, sort_keys=True))
        return 124
    if result.returncode != 0:
        output_text = result.stdout + "\n" + result.stderr
        next_actions = preflight_next_actions(output_text)
        reason = "preflight-command-failed"
        payload = {
            "ok": False,
            "reason": reason,
            "error": {"code": preflight_error_code(reason, output_text)},
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
                    "error": {"code": "missing-required-commands"},
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
    parser.add_argument("--bind", action="append", default=[], help="Additional Singularity bind spec, such as host:container:ro.")
    parser.add_argument(
        "--prepend-path",
        action="append",
        default=[],
        help="Prepend this path inside the container PATH. Repeatable.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the container command as JSON without executing it.")
    parser.add_argument(
        "--timeout-seconds",
        type=positive_timeout_seconds,
        help="Maximum seconds for the live container command after preflight. Emits structured JSON and exits 124 on timeout.",
    )
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
        "extra_binds": args.bind,
        "prepend_path": args.prepend_path,
        "state_dir": str(dirs["state_dir"]),
        "home_dir": str(dirs["home_dir"]),
        "cache_dir": str(dirs["cache_dir"]),
        "channel_dir": str(dirs["channel_dir"]),
        "host_env": host_env(dirs),
        "repo_root": str(resolve_path(args.repo_root)),
        "workspace": str(resolve_path(args.workspace)),
        "image": str(args.image),
        "timeout_seconds": args.timeout_seconds,
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
    try:
        process = subprocess.Popen(command, env=env, start_new_session=True)
        return process.wait(timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        terminate_process_group(process)
        print(json.dumps(container_timeout_payload(args, dirs, command, exc), indent=2, sort_keys=True))
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
