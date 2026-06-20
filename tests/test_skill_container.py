import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "skill_container.py"
SKILL_SCRIPT = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "skill_container.py"


def run(command):
    return subprocess.run(
        [str(part) for part in command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_skill_container_dry_run_builds_isolated_singularity_command(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    channel_dir = tmp_path / "channel"
    workspace.mkdir()

    result = run(
        [
            sys.executable,
            SCRIPT,
            "--dry-run",
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--channel",
            channel_dir,
            "--singularity-bin",
            "/opt/singularity-ce/4.1.1/bin/singularity",
            "--image",
            "docker://ubuntu:24.04",
            "--require-command",
            "python3",
            "--",
            "bash",
            "-lc",
            "echo ok",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    command = data["command"]
    preflight_command = data["preflight_command"]
    command_text = " ".join(command)
    assert command[:4] == [
        "/opt/singularity-ce/4.1.1/bin/singularity",
        "exec",
        "--cleanenv",
        "--containall",
    ]
    assert f"{state_dir.resolve() / 'home'}:/tmp/skill-home" in command
    assert f"{REPO_ROOT}:/mnt/skills:ro" in command
    assert f"{workspace.resolve()}:/mnt/project" in command
    assert f"{channel_dir.resolve()}:/tmp/skill-channel" in command
    assert "HOME=/tmp/skill-home" in command
    assert "PIXI_HOME=/tmp/skill-home/.pixi" in command
    assert "XDG_CACHE_HOME=/tmp/skill-home/.cache" in command
    assert "RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler" in command
    assert "CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel" in command
    assert command[-3:] == ["bash", "-lc", "echo ok"]
    assert data["required_commands"] == ["python3"]
    assert preflight_command[-5:] == [
        "sh",
        "-lc",
        "for command_name in \"$@\"; do command -v \"$command_name\" >/dev/null 2>&1 || printf '%s\\n' \"$command_name\"; done",
        "preflight",
        "python3",
    ]
    assert "/root" not in command_text
    assert data["workspace"] == str(workspace.resolve())
    assert data["channel_dir"] == str(channel_dir.resolve())


def test_skill_container_dry_run_creates_isolated_state_dirs(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()

    result = run(
        [
            sys.executable,
            SCRIPT,
            "--dry-run",
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--",
            "true",
        ]
    )

    assert result.returncode == 0, result.stdout
    assert (state_dir / "home").is_dir()
    assert (state_dir / "home" / ".cache").is_dir()
    assert (state_dir / "channel").is_dir()


def test_skill_container_default_image_has_python_for_planner(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()

    result = run(
        [
            sys.executable,
            SCRIPT,
            "--dry-run",
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--",
            "true",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["image"] == "docker://python:3.12-slim"
    assert "docker://python:3.12-slim" in data["command"]


def test_skill_container_dry_run_isolates_singularity_host_cache(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()

    result = run(
        [
            sys.executable,
            SCRIPT,
            "--dry-run",
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--",
            "true",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["host_env"]["SINGULARITY_CACHEDIR"] == str((state_dir / "singularity-cache").resolve())
    assert data["host_env"]["SINGULARITY_TMPDIR"] == str((state_dir / "singularity-tmp").resolve())
    assert (state_dir / "singularity-cache").is_dir()
    assert (state_dir / "singularity-tmp").is_dir()


def test_skill_container_preflight_reports_missing_required_commands(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    fake_singularity = tmp_path / "singularity"
    workspace.mkdir()
    fake_singularity.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
while [[ $# -gt 0 ]]; do
  case "$1" in
    exec|--cleanenv|--containall)
      shift
      ;;
    --home|--bind)
      shift 2
      ;;
    docker://*)
      shift
      break
      ;;
    *)
      shift
      ;;
  esac
done
exec "$@"
""",
        encoding="utf-8",
    )
    fake_singularity.chmod(0o755)

    result = run(
        [
            sys.executable,
            SCRIPT,
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--singularity-bin",
            fake_singularity,
            "--require-command",
            "definitely-missing-monata-tool",
            "--",
            "true",
        ]
    )

    assert result.returncode == 127
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["reason"] == "missing-required-commands"
    assert data["missing"] == ["definitely-missing-monata-tool"]
    assert data["required_commands"] == ["definitely-missing-monata-tool"]
    assert data["next_actions"][0]["id"] == "choose-container-with-required-commands"
    assert data["next_actions"][0]["requires_user_input"] is True


def test_skill_container_preflight_suggests_local_image_after_registry_failure(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    fake_singularity = tmp_path / "singularity"
    workspace.mkdir()
    fake_singularity.write_text(
        """#!/usr/bin/env bash
echo 'FATAL: Unable to handle docker://ubuntu:24.04 uri: failed to get checksum: Get "https://index.docker.io/v2/": EOF' >&2
exit 255
""",
        encoding="utf-8",
    )
    fake_singularity.chmod(0o755)

    result = run(
        [
            sys.executable,
            SCRIPT,
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--singularity-bin",
            fake_singularity,
            "--image",
            "docker://ubuntu:24.04",
            "--require-command",
            "python3",
            "--",
            "true",
        ]
    )

    assert result.returncode == 255
    data = json.loads(result.stdout)
    assert data["reason"] == "preflight-command-failed"
    assert data["next_actions"][0]["id"] == "use-local-container-image"
    assert data["next_actions"][0]["requires_user_input"] is True
    assert "local .sif" in data["next_actions"][0]["prompt"]


def test_monata_env_skill_installs_local_container_runner(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()

    result = run(
        [
            sys.executable,
            SKILL_SCRIPT,
            "--dry-run",
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--",
            "true",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["repo_root"].endswith("plugins/monata-env/skills/monata-env")
    assert "plugins/monata-env" in " ".join(data["command"])
