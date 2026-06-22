import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "monata-env"
    / "skills"
    / "monata-env"
    / "scripts"
    / "run_live_build_validation.py"
)
LIVE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "monata-env-live-build.yml"


def run(command):
    return subprocess.run(
        [str(part) for part in command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def test_live_build_validation_dry_run_exposes_build_upstream_command_and_artifacts(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    state_dir = tmp_path / "state"
    image = tmp_path / "monata-env-test.sif"
    host_pixi_root = tmp_path / "host-pixi"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    workspace.mkdir()
    (workspace / "pyproject.toml").write_text('[project]\nname = "monata"\n', encoding="utf-8")
    (output_dir / "linux-64").mkdir(parents=True)
    (output_dir / "linux-64" / "ngspice-46.0-hb0f4dca_0.conda").write_text("", encoding="utf-8")
    (output_dir / "linux-64" / "openvaf-r-0.4.0-hb0f4dca_0.conda").write_text("", encoding="utf-8")
    for source in (klayout_source, xschem_source):
        source.mkdir()
    (host_pixi_root / "bin").mkdir(parents=True)
    image.write_text("sif", encoding="utf-8")

    result = run(
        [
            sys.executable,
            SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--container-state-dir",
            state_dir,
            "--container-image",
            image,
            "--host-pixi-root",
            host_pixi_root,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--dry-run",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["command_key"] == "build_install_smoke_upstream"
    assert "run_live_build_validation.py" not in data["command"]
    assert "execute_monata_env_runbook.py" in data["command"]
    assert "--step check_channel --step build --step install --step smoke --step upstream_installed_tests --step audit" in data[
        "command"
    ]
    assert data["artifacts"]["host_manifest"] == str(session_dir.resolve() / "monata-env-install-manifest.json")
    assert data["artifacts"]["container_session_dir"] == str(state_dir.resolve() / "home" / "monata-env-session")
    assert data["artifacts"]["channel_dir"] == str(output_dir.resolve())


def test_live_build_validation_workflow_is_manual_and_uploads_artifacts():
    text = LIVE_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "run_live_build_validation.py" in text
    assert "actions/upload-artifact" in text
    assert "monata-env-live-build-artifacts" in text
