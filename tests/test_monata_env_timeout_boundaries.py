import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "plan_monata_env.py"
CONTAINER_SCRIPT = REPO_ROOT / "scripts" / "skill_container.py"


def run(command):
    return subprocess.run(
        [str(part) for part in command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_plan_rejects_non_positive_live_timeout_seconds(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    workspace.mkdir()

    for value in ("0", "-1"):
        result = run(
            [
                sys.executable,
                PLAN_SCRIPT,
                "--root",
                workspace,
                "--output-dir",
                output_dir,
                "--live-timeout-seconds",
                value,
            ]
        )

        assert result.returncode == 2
        assert "--live-timeout-seconds must be a positive integer" in result.stdout


def test_plan_rejects_non_numeric_live_timeout_seconds(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    workspace.mkdir()

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--live-timeout-seconds",
            "not-a-number",
        ]
    )

    assert result.returncode == 2
    assert "--live-timeout-seconds must be a positive integer" in result.stdout


def test_container_rejects_non_positive_timeout_seconds(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()

    for value in ("0", "-5"):
        result = run(
            [
                sys.executable,
                CONTAINER_SCRIPT,
                "--dry-run",
                "--state-dir",
                state_dir,
                "--workspace",
                workspace,
                "--timeout-seconds",
                value,
                "--",
                "true",
            ]
        )

        assert result.returncode == 2
        assert "--timeout-seconds must be a positive integer" in result.stdout


def test_container_rejects_non_numeric_timeout_seconds(tmp_path):
    workspace = tmp_path / "workspace"
    state_dir = tmp_path / "state"
    workspace.mkdir()

    result = run(
        [
            sys.executable,
            CONTAINER_SCRIPT,
            "--dry-run",
            "--state-dir",
            state_dir,
            "--workspace",
            workspace,
            "--timeout-seconds",
            "not-a-number",
            "--",
            "true",
        ]
    )

    assert result.returncode == 2
    assert "--timeout-seconds must be a positive integer" in result.stdout
