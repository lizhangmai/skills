#!/usr/bin/env python
"""Prepare a Singularity image for isolated monata-env live tests."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


DEFAULT_SINGULARITY_BIN = "/opt/singularity-ce/4.1.1/bin/singularity"
DEFAULT_BASE_IMAGE = "docker://python:3.12-slim"
REQUIRED_COMMANDS = ["python3", "git", "pixi"]
PREFLIGHT_SCRIPT = "command -v python3 && command -v git && command -v pixi"


def resolve(path):
    return Path(path).expanduser().resolve()


def definition_text(base_image, pixi_binary=None):
    pixi_binary = resolve(pixi_binary) if pixi_binary else None
    files = ""
    install_pixi = (
        "    chmod 0755 /usr/local/bin/pixi\n"
        if pixi_binary
        else (
            "    curl -fsSL https://pixi.sh/install.sh | PIXI_HOME=/opt/pixi sh\n"
            "    ln -sf /opt/pixi/bin/pixi /usr/local/bin/pixi\n"
        )
    )
    if pixi_binary:
        files = f"\n%files\n    {pixi_binary} /usr/local/bin/pixi\n"
    return f"""Bootstrap: docker
From: {base_image.removeprefix("docker://")}

%post
    set -eux
    apt-get update
    apt-get install -y --no-install-recommends \\
        ca-certificates \\
        curl \\
        git \\
        bash \\
        xz-utils \\
        bzip2
    rm -rf /var/lib/apt/lists/*
{install_pixi}
%environment
    export PATH=/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin
{files}
%test
    command -v python3
    command -v git
    command -v pixi
    python3 --version
    git --version
    pixi --version
"""


def build_command(args):
    command = [str(args.singularity_bin), "build"]
    if args.remote:
        command.append("--remote")
    elif not args.no_fakeroot:
        command.append("--fakeroot")
    command.append("--force")
    command.extend([str(args.image), str(args.definition)])
    return command


def preflight_command(args):
    return [str(args.singularity_bin), "exec", str(args.image), "sh", "-c", PREFLIGHT_SCRIPT]


def run(command):
    return subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def next_actions_for_build_failure(build_item):
    text = (build_item.get("stdout", "") + "\n" + build_item.get("stderr", "")).lower()
    if any(token in text for token in ("could not use fakeroot", "/etc/subuid", "proot command", "non-root user")):
        return [
            {
                "id": "enable-fakeroot-or-use-remote-build",
                "title": "Enable Singularity fakeroot or use remote build",
                "requires_user_input": True,
                "prompt": "The local Singularity install cannot build this image as the current non-root user. Ask an administrator to add subuid/subgid mappings for this user, use a configured remote builder, or provide a prebuilt .sif image.",
            },
            {
                "id": "use-host-pixi-bind-fallback",
                "title": "Use host pixi bind fallback",
                "requires_user_input": False,
                "prompt": "Continue live validation with plan.container.live_install_smoke_command or install_smoke_upstream_command, which binds only the host pixi executable and keeps pixi state isolated in the container HOME.",
            },
        ]
    return [
        {
            "id": "inspect-image-build-log",
            "title": "Inspect image build log",
            "requires_user_input": False,
            "prompt": "The test image build failed. Inspect stdout/stderr, then retry with a local pixi binary, a different base image, remote build, or a user-provided .sif.",
        }
    ]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True, help="Output .sif path.")
    parser.add_argument("--definition", type=Path, help="Definition file path.")
    parser.add_argument("--base-image", default=DEFAULT_BASE_IMAGE, help="Docker base image for the test container.")
    parser.add_argument("--pixi-binary", type=Path, help="Optional local pixi binary to copy into the image.")
    parser.add_argument("--singularity-bin", default=DEFAULT_SINGULARITY_BIN)
    parser.add_argument("--no-fakeroot", action="store_true", help="Build without --fakeroot.")
    parser.add_argument("--remote", action="store_true", help="Use the configured Singularity remote builder.")
    parser.add_argument("--dry-run", action="store_true", help="Write the definition and print planned commands.")
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    args = parser.parse_args()
    args.image = resolve(args.image)
    args.definition = resolve(args.definition) if args.definition else args.image.with_suffix(".def")
    args.singularity_bin = str(args.singularity_bin)
    if args.pixi_binary:
        args.pixi_binary = resolve(args.pixi_binary)
    return args


def payload(args, build=None, preflight=None):
    data = {
        "image": str(args.image),
        "definition": str(args.definition),
        "base_image": args.base_image,
        "pixi_binary": str(args.pixi_binary) if args.pixi_binary else "",
        "required_commands": REQUIRED_COMMANDS,
        "build_command": build_command(args),
        "preflight_command": preflight_command(args),
        "dry_run": args.dry_run,
        "remote": args.remote,
        "no_fakeroot": args.no_fakeroot,
    }
    if build is not None:
        data["build"] = build
    if preflight is not None:
        data["preflight"] = preflight
    return data


def print_payload(args, data):
    if args.format == "json":
        print(json.dumps(data, indent=2, sort_keys=True))
        return
    print(f"image: {data['image']}")
    print(f"definition: {data['definition']}")
    print("build: " + " ".join(data["build_command"]))
    print("preflight: " + " ".join(data["preflight_command"]))


def main():
    args = parse_args()
    args.definition.parent.mkdir(parents=True, exist_ok=True)
    args.image.parent.mkdir(parents=True, exist_ok=True)
    args.definition.write_text(definition_text(args.base_image, args.pixi_binary), encoding="utf-8")

    if args.dry_run:
        print_payload(args, payload(args))
        return 0

    build = run(build_command(args))
    build_item = {
        "returncode": build.returncode,
        "stdout": build.stdout[-4000:],
        "stderr": build.stderr[-4000:],
    }
    preflight_item = None
    if build.returncode == 0:
        preflight = run(preflight_command(args))
        preflight_item = {
            "returncode": preflight.returncode,
            "stdout": preflight.stdout[-4000:],
            "stderr": preflight.stderr[-4000:],
        }
    data = payload(args, build=build_item, preflight=preflight_item)
    if build.returncode != 0:
        data["next_actions"] = next_actions_for_build_failure(build_item)
    print_payload(args, data)
    if build.returncode != 0:
        return build.returncode
    return 0 if preflight_item and preflight_item["returncode"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
