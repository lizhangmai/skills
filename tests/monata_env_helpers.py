import json
import os
import shlex
import subprocess
import sys
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "plan_monata_env.py"
SMOKE_SCRIPT = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "smoke_monata_env_tools.py"
UPSTREAM_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "test_monata_env_upstream.py"
)
EXECUTE_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "execute_monata_env_runbook.py"
)
REPLAY_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "replay_monata_env_negotiation.py"
)
PREPARE_IMAGE_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "prepare_monata_env_test_image.py"
)
RECORD_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "record_monata_env_session.py"
)
AUDIT_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "audit_monata_env_manifest.py"
)
RATTLER_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "conda-build"
    / "skills"
    / "conda-build"
    / "scripts"
    / "rattler_channel.py"
)


def run(command, **kwargs):
    return subprocess.run(
        [str(part) for part in command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        **kwargs,
    )


def git_repo_with_tagged_parent(path: Path, tag: str) -> None:
    path.mkdir(parents=True)
    run(["git", "init", path])
    (path / "source.txt").write_text("tagged\n", encoding="utf-8")
    run(["git", "-C", path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", "source.txt"])
    run(
        [
            "git",
            "-C",
            path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "tagged",
        ]
    )
    run(["git", "-C", path, "tag", tag])
    (path / "source.txt").write_text("newer\n", encoding="utf-8")
    run(["git", "-C", path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", "source.txt"])
    run(
        [
            "git",
            "-C",
            path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "newer",
        ]
    )


def git_repo_with_uninitialized_submodule(path: Path, tag: str, submodule_source: Path) -> None:
    submodule_source.mkdir(parents=True)
    run(["git", "init", submodule_source])
    (submodule_source / "source.txt").write_text("submodule\n", encoding="utf-8")
    run(["git", "-C", submodule_source, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", "source.txt"])
    run(
        [
            "git",
            "-C",
            submodule_source,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "submodule-source",
        ]
    )
    path.mkdir(parents=True)
    run(["git", "init", path])
    run(
        [
            "git",
            "-C",
            path,
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(submodule_source),
            "deps/model",
        ]
    )
    run(["git", "-C", path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", "."])
    run(
        [
            "git",
            "-C",
            path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "tagged-with-submodule",
        ]
    )
    run(["git", "-C", path, "tag", tag])
    run(["git", "-C", path, "submodule", "deinit", "-f", "deps/model"])


def write_monata_workspace(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "pyproject.toml").write_text('[project]\nname = "monata"\n', encoding="utf-8")


def write_manifest_seed(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plan": {"mode": "ai-native-session", "env_name": "monata-env"},
                "execution": {"commands_run": [], "artifacts": []},
                "verification": {"smoke": None, "upstream_installed": None},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_auditable_manifest(
    path: Path,
    *,
    plan: dict | None = None,
    smoke: dict | None = None,
    artifacts: list[dict] | None = None,
) -> None:
    tools = ["ngspice", "openvaf-r", "klayout", "xschem"]
    path.parent.mkdir(parents=True)
    manifest_plan = plan or {
        "mode": "ai-native-session",
        "env_name": "monata-env",
        "packages": tools,
        "commands": {
            "install": [
                "pixi",
                "global",
                "install",
                "--environment",
                "monata-env",
                "--expose",
                "ngspice=ngspice",
                "--expose",
                "openvaf-r=openvaf-r",
                "--expose",
                "klayout=klayout",
                "--expose",
                "xschem=xschem",
            ],
            "smoke": [sys.executable, str(SMOKE_SCRIPT), "--format", "json"],
        },
        "test_profiles": {
            "upstream_installed": {"recommended": False},
        },
    }
    smoke_payload = smoke or {
        "ok": True,
        "tools": {tool: {"ok": True, "reason": "ok", "path": f"/tmp/bin/{tool}"} for tool in tools},
    }
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "plan": manifest_plan,
                "execution": {
                    "commands_run": [
                        {
                            "kind": "install",
                            "command": "pixi global install --environment monata-env",
                            "returncode": 0,
                        },
                        {
                            "kind": "smoke",
                            "command": f"{sys.executable} {SMOKE_SCRIPT} --format json",
                            "returncode": 0,
                        },
                    ],
                    "artifacts": artifacts or [],
                },
                "verification": {
                    "smoke": smoke_payload,
                    "upstream_installed": None,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def write_channel_artifacts(output_dir: Path, packages: list[str]) -> None:
    linux64 = output_dir / "linux-64"
    linux64.mkdir(parents=True)
    versions = {
        "ngspice": "46.0",
        "openvaf-r": "0.4.0",
        "klayout": "0.30.9",
        "xschem": "3.4.7",
    }
    for package in packages:
        (linux64 / f"{package}-{versions[package]}-hb0f4dca_0.conda").write_text("", encoding="utf-8")


def write_source_archive(path: Path, top_dir: str = "source") -> None:
    source_root = path.parent / top_dir
    source_root.mkdir(parents=True)
    (source_root / "README.md").write_text("local source archive\n", encoding="utf-8")
    with tarfile.open(path, "w:gz") as archive:
        archive.add(source_root, arcname=top_dir)


def write_executable(path: Path, text: str = "#!/usr/bin/env sh\nexit 0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)
