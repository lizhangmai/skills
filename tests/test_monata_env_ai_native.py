import json
import os
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


def test_plan_reports_ref_mismatch_and_recommended_commands(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_source = tmp_path / "klayout"
    write_monata_workspace(workspace)
    (output_dir / "linux-64").mkdir(parents=True)
    (output_dir / "linux-64" / "ngspice-46.0-hb0f4dca_0.conda").write_text("", encoding="utf-8")
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--local-source",
            f"klayout={klayout_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["mode"] == "ai-native-session"
    assert data["packages"] == ["ngspice", "openvaf-r", "klayout", "xschem"]
    assert data["channel"]["packages"]["ngspice"]["present"] is True
    assert data["channel"]["packages"]["klayout"]["present"] is False
    assert data["local_sources"]["klayout"]["status"] == "ref-mismatch"
    assert data["local_sources"]["klayout"]["target_ref"] == "v0.30.9"
    assert data["questions"][0]["id"] == "local_source_worktree"
    assert data["questions"][0]["worktree_commands"]["klayout"] == data["local_sources"]["klayout"]["worktree_command"]
    assert data["questions"][0]["recommended_sources"]["klayout"] == data["local_sources"]["klayout"]["recommended_worktree"]
    assert data["questions"][0]["replan_local_sources"] == [
        f"klayout={data['local_sources']['klayout']['recommended_worktree']}"
    ]
    build_command = " ".join(data["commands"]["build"])
    assert "--local-source" in build_command
    assert "klayout=" in build_command
    assert "--local-source-ref" in build_command
    assert "klayout=v0.30.9" in build_command
    assert data["manifest"]["path"].endswith("monata-env-install-manifest.json")


def test_plan_reports_git_unavailable_for_local_source_validation(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_source = tmp_path / "klayout"
    write_monata_workspace(workspace)
    klayout_source.mkdir()

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--local-source",
            f"klayout={klayout_source}",
            "--format",
            "json",
        ],
        env={"PATH": ""},
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["local_sources"]["klayout"]["status"] == "git-unavailable"
    assert data["questions"][0]["id"] == "local_source_repair"
    assert data["questions"][0]["problem_sources"]["klayout"]["status"] == "git-unavailable"
    assert data["questions"][0]["problem_sources"]["klayout"]["path"] == str(klayout_source.resolve())
    assert data["questions"][0]["problem_sources"]["klayout"]["target_ref"] == "v0.30.9"


def test_plan_accepts_local_source_archive_without_git_ref_validation(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_archive = tmp_path / "klayout-v0.30.9.tar.gz"
    write_monata_workspace(workspace)
    write_source_archive(klayout_archive, "klayout-0.30.9")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--local-source",
            f"klayout={klayout_archive}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["local_sources"]["klayout"]["status"] == "archive"
    assert data["local_sources"]["klayout"]["source_kind"] == "archive"
    assert data["local_sources"]["klayout"]["target_ref"] == "v0.30.9"
    assert data["questions"][0]["id"] == "local_source_archive_trust"
    assert data["questions"][0]["archive_sources"]["klayout"]["path"] == str(klayout_archive.resolve())
    build_command = " ".join(data["commands"]["build"])
    assert f"--local-source klayout={klayout_archive.resolve()}" in build_command
    assert "--local-source-ref klayout=v0.30.9" not in build_command
    assert data["commands"]["upstream_installed_tests"] == []
    assert data["test_profiles"]["upstream_installed"]["recommended"] is False


def test_plan_skips_build_when_existing_channel_has_local_source_packages(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    write_channel_artifacts(output_dir, ["ngspice", "openvaf-r", "klayout", "xschem"])
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["channel"]["missing"] == []
    assert data["build_needed"] is False
    assert data["build_packages"] == []
    assert data["commands"]["build"] == []

    runbook = {step["id"]: step for step in data["runbook"]}
    assert runbook["build"]["recommended"] is False
    assert runbook["build"]["record_after"] is None
    check_record = " ".join(runbook["check_channel"]["record_after"]["command"])
    assert f"--artifact-dir {output_dir.resolve()}" in check_record
    for package in ("ngspice", "openvaf-r", "klayout", "xschem"):
        assert f"--package {package}" in check_record
    assert runbook["install"]["depends_on"] == ["check_channel"]

    decisions = {decision["id"]: decision for decision in data["decisions"]}
    source_options = {option["id"]: option for option in decisions["source_policy"]["options"]}
    assert decisions["source_policy"]["default"] == "existing_channel_only"
    assert source_options["existing_channel_only"]["recommended"] is True
    assert source_options["local_sources"]["recommended"] is False


def test_plan_session_dir_keeps_logs_and_manifest_separate_from_channel(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    write_monata_workspace(workspace)
    write_channel_artifacts(output_dir, ["ngspice", "openvaf-r", "klayout", "xschem"])

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["channel"]["output_dir"] == str(output_dir.resolve())
    assert data["session"]["dir"] == str(session_dir.resolve())
    assert data["manifest"]["path"] == str(session_dir.resolve() / "monata-env-install-manifest.json")

    runbook = {step["id"]: step for step in data["runbook"]}
    assert runbook["check_channel"]["stdout_path"] == str(session_dir.resolve() / "monata-env-check-channel.json")
    assert runbook["install"]["stdout_path"] == str(session_dir.resolve() / "monata-env-install.out")
    check_record = " ".join(runbook["check_channel"]["record_after"]["command"])
    assert f"--artifact-dir {output_dir.resolve()}" in check_record
    assert f"--manifest {session_dir.resolve() / 'monata-env-install-manifest.json'}" in check_record


def test_plan_recommends_upstream_installed_tests_when_sources_are_provided(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["test_profiles"]["upstream_installed"]["recommended"] is True
    assert data["test_profiles"]["upstream_installed"]["requires_local_source"] is True
    command = " ".join(data["commands"]["upstream_installed_tests"])
    assert "test_monata_env_upstream.py" in command
    assert f"--klayout-source {klayout_source.resolve()}" in command
    assert f"--xschem-source {xschem_source.resolve()}" in command


def test_plan_keeps_upstream_installed_test_work_dir_under_session_dir(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    command = " ".join(data["commands"]["upstream_installed_tests"])
    work_dir = session_dir.resolve() / "monata-env-upstream-work"
    assert f"--work-dir {work_dir}" in command
    assert "--keep-work-dir" in command


def test_plan_can_select_full_upstream_installed_profile(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    image = tmp_path / "monata-env-python.sif"
    host_pixi_root = tmp_path / "host-pixi"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    image.write_text("sif", encoding="utf-8")
    (host_pixi_root / "bin").mkdir(parents=True)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--container-image",
            image,
            "--host-pixi-root",
            host_pixi_root,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--upstream-profile",
            "full",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["upstream_profile"] == "full"
    command = " ".join(data["commands"]["upstream_installed_tests"])
    assert "--profile full" in command
    runbook = {step["id"]: step for step in data["runbook"]}
    assert runbook["upstream_installed_tests"]["timeout_seconds"] == 7200
    decisions = {decision["id"]: decision for decision in data["decisions"]}
    assert decisions["upstream_test_profile"]["default"] == "full"
    profile_options = {option["id"]: option for option in decisions["upstream_test_profile"]["options"]}
    assert profile_options["basic"]["recommended"] is False
    assert profile_options["full"]["recommended"] is True
    upstream = {option["id"]: option for option in decisions["test_isolation"]["options"]}["singularity"]["commands"][
        "install_smoke_upstream"
    ]
    assert "--upstream-profile full" in upstream
    assert "--step check_channel --step install --step smoke --step upstream_installed_tests --step audit" in upstream


def test_plan_threads_custom_env_name_into_upstream_and_container_commands(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    image = tmp_path / "monata-env-python.sif"
    host_pixi_root = tmp_path / "host-pixi"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    image.write_text("sif", encoding="utf-8")
    (host_pixi_root / "bin").mkdir(parents=True)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--container-image",
            image,
            "--host-pixi-root",
            host_pixi_root,
            "--env-name",
            "custom-monata-env",
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["env_name"] == "custom-monata-env"
    assert "--environment custom-monata-env" in " ".join(data["commands"]["install"])
    assert "--env-name custom-monata-env" in " ".join(data["commands"]["upstream_installed_tests"])

    decisions = {decision["id"]: decision for decision in data["decisions"]}
    assert "custom-monata-env" in decisions["global_environment"]["prompt"]
    global_options = {option["id"]: option for option in decisions["global_environment"]["options"]}
    assert global_options["approve"]["label"] == "Update custom-monata-env"
    singularity = {option["id"]: option for option in decisions["test_isolation"]["options"]}["singularity"]
    assert "--env-name custom-monata-env" in singularity["command"]
    assert "--env-name custom-monata-env" in singularity["commands"]["install_smoke"]
    assert "--env-name custom-monata-env" in singularity["commands"]["install_smoke_upstream"]


def test_plan_uses_available_conda_build_helper_path(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    write_monata_workspace(workspace)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["helper"]["conda_build_script"] == str(RATTLER_SCRIPT)
    assert data["helper"]["conda_build_script_exists"] is True
    assert data["commands"]["check_channel"][1] == str(RATTLER_SCRIPT)
    assert data["commands"]["build"][1] == str(RATTLER_SCRIPT)


def test_plan_runbook_records_build_install_and_smoke_steps(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    write_monata_workspace(workspace)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    runbook = {step["id"]: step for step in data["runbook"]}
    assert list(runbook)[:4] == ["check_channel", "build", "install", "smoke"]

    build_step = runbook["build"]
    build_stdout = output_dir.resolve() / "monata-env-build.out"
    build_stderr = output_dir.resolve() / "monata-env-build.err"
    assert build_step["recommended"] is True
    assert build_step["timeout_seconds"] == 7200
    assert build_step["command"] == data["commands"]["build"]
    assert build_step["stdout_path"] == str(build_stdout)
    assert build_step["stderr_path"] == str(build_stderr)
    assert build_step["record_after"]["returncode_var"] == "BUILD_RC"
    build_record = " ".join(build_step["record_after"]["command"])
    assert "record_monata_env_session.py" in build_record
    assert "--command-kind build" in build_record
    assert f"--stdout-file {build_stdout}" in build_record
    assert f"--stderr-file {build_stderr}" in build_record
    assert f"--artifact-dir {output_dir.resolve()}" in build_record
    assert "--package ngspice" in build_record
    assert "--package openvaf-r" in build_record
    assert "--package klayout" in build_record
    assert "--package xschem" in build_record

    install_step = runbook["install"]
    assert install_step["depends_on"] == ["build"]
    assert install_step["timeout_seconds"] == 1800
    assert install_step["stdout_path"] == str(output_dir.resolve() / "monata-env-install.out")
    assert install_step["stderr_path"] == str(output_dir.resolve() / "monata-env-install.err")
    assert install_step["status_path"] == str(output_dir.resolve() / "monata-env-install.status.json")
    assert install_step["record_after"]["returncode_var"] == "INSTALL_RC"
    assert "--command-kind install" in " ".join(install_step["record_after"]["command"])

    smoke_step = runbook["smoke"]
    assert smoke_step["depends_on"] == ["install"]
    assert smoke_step["timeout_seconds"] == 600
    smoke_json = output_dir.resolve() / "monata-env-smoke.json"
    smoke_stderr = output_dir.resolve() / "monata-env-smoke.err"
    assert smoke_step["stdout_path"] == str(smoke_json)
    assert smoke_step["stderr_path"] == str(smoke_stderr)
    assert smoke_step["status_path"] == str(output_dir.resolve() / "monata-env-smoke.status.json")
    assert smoke_step["record_after"]["returncode_var"] == "SMOKE_RC"
    smoke_record = " ".join(smoke_step["record_after"]["command"])
    assert "--command-kind smoke" in smoke_record
    assert f"--stdout-file {smoke_json}" in smoke_record
    assert f"--stderr-file {smoke_stderr}" in smoke_record
    assert f"--verification smoke={smoke_json}" in smoke_record

    audit_step = runbook["audit"]
    audit_json = output_dir.resolve() / "monata-env-audit.json"
    audit_stderr = output_dir.resolve() / "monata-env-audit.err"
    assert audit_step["depends_on"] == ["smoke"]
    assert audit_step["timeout_seconds"] == 120
    assert audit_step["stdout_path"] == str(audit_json)
    assert audit_step["stderr_path"] == str(audit_stderr)
    assert "audit_monata_env_manifest.py" in " ".join(audit_step["command"])
    assert "--check-live" in audit_step["command"]
    assert f"--manifest {output_dir.resolve() / 'monata-env-install-manifest.json'}" in " ".join(
        audit_step["command"]
    )
    assert audit_step["record_after"]["returncode_var"] == "AUDIT_RC"
    audit_record = " ".join(audit_step["record_after"]["command"])
    assert "--command-kind audit" in audit_record
    assert f"--stdout-file {audit_json}" in audit_record
    assert f"--stderr-file {audit_stderr}" in audit_record
    assert f"--verification audit={audit_json}" in audit_record


def test_plan_runbook_records_optional_upstream_installed_tests(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    runbook = {step["id"]: step for step in data["runbook"]}
    upstream_step = runbook["upstream_installed_tests"]
    upstream_json = output_dir.resolve() / "monata-env-upstream-installed.json"
    assert upstream_step["depends_on"] == ["smoke"]
    assert upstream_step["recommended"] is True
    assert upstream_step["requires_confirmation"] is True
    assert upstream_step["command"] == data["commands"]["upstream_installed_tests"]
    assert upstream_step["stdout_path"] == str(upstream_json)
    upstream_record = " ".join(upstream_step["record_after"]["command"])
    assert "--command-kind upstream_installed_tests" in upstream_record
    assert f"--stdout-file {upstream_json}" in upstream_record
    assert f"--verification upstream_installed={upstream_json}" in upstream_record


def test_plan_decisions_offer_network_source_and_isolated_testing_defaults(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    write_monata_workspace(workspace)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    decisions = {decision["id"]: decision for decision in data["decisions"]}
    assert decisions["source_policy"]["default"] == "network"
    source_options = {option["id"]: option for option in decisions["source_policy"]["options"]}
    assert source_options["network"]["recommended"] is True
    assert source_options["local_sources"]["recommended"] is False
    assert data["commands"]["upstream_installed_tests"] == []
    runbook = {step["id"]: step for step in data["runbook"]}
    assert runbook["upstream_installed_tests"]["record_after"] is None
    assert decisions["test_isolation"]["default"] == "singularity"
    isolation_options = {option["id"]: option for option in decisions["test_isolation"]["options"]}
    assert isolation_options["singularity"]["recommended"] is True
    isolation_command = isolation_options["singularity"]["command"]
    assert "scripts/skill_container.py" in isolation_command
    assert f"--repo-root {REPO_ROOT}" in isolation_command
    assert "--image docker://python:3.12-slim" in isolation_command
    assert "--require-command python3" in isolation_command
    assert "--session-dir /tmp/skill-home/monata-env-session" in isolation_command
    assert "/mnt/skills/plugins/monata-env/skills/monata-env/scripts/plan_monata_env.py" in isolation_command
    assert "--conda-build-helper /mnt/skills/plugins/conda-build/skills/conda-build/scripts/rattler_channel.py" in isolation_command
    assert decisions["upstream_test_profile"]["default"] == "skip"


def test_plan_decisions_accept_local_container_image_for_isolated_testing(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    image = tmp_path / "monata-env-python.sif"
    write_monata_workspace(workspace)
    image.write_text("sif", encoding="utf-8")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--container-image",
            image,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    decisions = {decision["id"]: decision for decision in data["decisions"]}
    command = {option["id"]: option for option in decisions["test_isolation"]["options"]}["singularity"]["command"]
    assert f"--image {image.resolve()}" in command
    assert "docker://python:3.12-slim" not in command


def test_plan_decisions_offer_dedicated_test_image_preparation(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    host_pixi_root = tmp_path / "host-pixi"
    test_image = session_dir / "monata-env-test.sif"
    write_monata_workspace(workspace)
    (host_pixi_root / "bin").mkdir(parents=True)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--host-pixi-root",
            host_pixi_root,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["container"]["test_image"]["image"] == str(test_image.resolve())
    assert data["container"]["test_image"]["required_commands"] == ["/usr/local/bin/python3", "git", "pixi"]
    assert "prepare_monata_env_test_image.py" in data["container"]["test_image"]["prepare_command"]
    assert f"--image {test_image.resolve()}" in data["container"]["test_image"]["prepare_command"]
    assert f"--pixi-binary {host_pixi_root.resolve() / 'bin' / 'pixi'}" in data["container"]["test_image"]["prepare_command"]
    assert "--remote" in data["container"]["test_image"]["remote_prepare_command"]
    assert f"--image {test_image.resolve()}" in data["container"]["test_image"]["remote_prepare_command"]
    assert "--pixi-binary" not in data["container"]["test_image"]["remote_prepare_command"]
    assert "scripts/skill_container.py" in data["container"]["test_image"]["validate_command"]
    assert f"--image {test_image.resolve()}" in data["container"]["test_image"]["validate_command"]
    assert "--require-command /usr/local/bin/python3" in data["container"]["test_image"]["validate_command"]
    assert "--require-command git" in data["container"]["test_image"]["validate_command"]
    assert "--require-command pixi" in data["container"]["test_image"]["validate_command"]

    decisions = {decision["id"]: decision for decision in data["decisions"]}
    image_options = {option["id"]: option for option in decisions["test_image"]["options"]}
    assert decisions["test_image"]["default"] == "prepare_dedicated"
    assert image_options["prepare_dedicated"]["recommended"] is True
    assert image_options["prepare_dedicated"]["command"] == data["container"]["test_image"]["prepare_command"]
    assert image_options["prepare_dedicated"]["remote_command"] == data["container"]["test_image"]["remote_prepare_command"]
    assert image_options["prepare_dedicated"]["validation_command"] == data["container"]["test_image"]["validate_command"]
    assert image_options["host_pixi_bind"]["recommended"] is True


def test_prepare_test_image_dry_run_writes_definition_with_local_pixi(tmp_path):
    image = tmp_path / "monata-env-test.sif"
    definition = tmp_path / "monata-env-test.def"
    pixi = tmp_path / "pixi"
    pixi.write_text("#!/bin/sh\n", encoding="utf-8")
    pixi.chmod(0o755)

    result = run(
        [
            sys.executable,
            PREPARE_IMAGE_SCRIPT,
            "--image",
            image,
            "--definition",
            definition,
            "--pixi-binary",
            pixi,
            "--dry-run",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["image"] == str(image.resolve())
    assert data["definition"] == str(definition.resolve())
    assert data["dry_run"] is True
    assert data["required_commands"] == ["python3", "git", "pixi"]
    assert data["build_command"][:3] == ["/opt/singularity-ce/4.1.1/bin/singularity", "build", "--fakeroot"]
    assert data["preflight_command"][-4:] == [str(image.resolve()), "sh", "-c", "command -v python3 && command -v git && command -v pixi"]
    text = definition.read_text(encoding="utf-8")
    assert "Bootstrap: docker" in text
    assert "From: python:3.12-slim" in text
    assert "apt-get install -y --no-install-recommends" in text
    assert " git " in text
    assert "%files" in text
    assert f"{pixi.resolve()} /usr/local/bin/pixi" in text
    assert "command -v python3" in text
    assert "command -v git" in text
    assert "command -v pixi" in text


def test_prepare_test_image_reports_fakeroot_mapping_next_actions(tmp_path):
    image = tmp_path / "monata-env-test.sif"
    definition = tmp_path / "monata-env-test.def"
    fake_singularity = tmp_path / "singularity"
    fake_singularity.write_text(
        "#!/usr/bin/env sh\n"
        "printf '%s\\n' 'FATAL:   could not use fakeroot: no mapping entry found in /etc/subuid for lizhangmai' >&2\n"
        "exit 255\n",
        encoding="utf-8",
    )
    fake_singularity.chmod(0o755)

    result = run(
        [
            sys.executable,
            PREPARE_IMAGE_SCRIPT,
            "--image",
            image,
            "--definition",
            definition,
            "--singularity-bin",
            fake_singularity,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 255, result.stdout
    data = json.loads(result.stdout)
    assert data["build"]["returncode"] == 255
    assert data["next_actions"][0]["id"] == "enable-fakeroot-or-use-remote-build"
    assert data["next_actions"][0]["requires_user_input"] is True
    assert data["next_actions"][1]["id"] == "use-host-pixi-bind-fallback"


def test_prepare_test_image_remote_build_omits_fakeroot(tmp_path):
    image = tmp_path / "monata-env-test.sif"

    result = run(
        [
            sys.executable,
            PREPARE_IMAGE_SCRIPT,
            "--image",
            image,
            "--remote",
            "--dry-run",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["build_command"][:3] == ["/opt/singularity-ce/4.1.1/bin/singularity", "build", "--remote"]
    assert "--fakeroot" not in data["build_command"]


def test_plan_decisions_can_emit_isolated_live_install_smoke_command(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    image = tmp_path / "monata-env-python.sif"
    host_pixi_root = tmp_path / "host-pixi"
    write_monata_workspace(workspace)
    write_channel_artifacts(output_dir, ["ngspice", "openvaf-r", "klayout", "xschem"])
    image.write_text("sif", encoding="utf-8")
    (host_pixi_root / "bin").mkdir(parents=True)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--container-image",
            image,
            "--host-pixi-root",
            host_pixi_root,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    decisions = {decision["id"]: decision for decision in data["decisions"]}
    singularity = {option["id"]: option for option in decisions["test_isolation"]["options"]}["singularity"]
    commands = singularity["commands"]
    assert commands["planner"] == singularity["command"]
    live_install = commands["install_smoke"]
    assert "scripts/skill_container.py" in live_install
    assert f"--state-dir {session_dir.resolve() / 'container-state'}" in live_install
    assert f"--image {image.resolve()}" in live_install
    assert f"--channel {output_dir.resolve()}" in live_install
    assert f"--bind {host_pixi_root.resolve() / 'bin' / 'pixi'}:/opt/host-pixi/bin/pixi:ro" in live_install
    assert f"--bind {host_pixi_root.resolve()}:/opt/host-pixi:ro" not in live_install
    assert "--prepend-path /tmp/skill-home/.pixi/bin --prepend-path /opt/host-pixi/bin" in live_install
    assert "--prepend-path /opt/host-pixi/bin" in live_install
    assert "--require-command /usr/local/bin/python3" in live_install
    assert "--require-command pixi" in live_install
    assert "bash -c" in live_install
    assert "bash -lc" not in live_install
    assert "plan_monata_env.py" in live_install
    assert "/usr/local/bin/python3 /mnt/skills/plugins/monata-env/skills/monata-env/scripts/plan_monata_env.py" in live_install
    assert "--root /mnt/project --output-dir /tmp/skill-channel" in live_install
    assert "--session-dir /tmp/skill-home/monata-env-session" in live_install
    assert "--write-manifest --format json" in live_install
    assert "execute_monata_env_runbook.py" in live_install
    assert "/usr/local/bin/python3 /mnt/skills/plugins/monata-env/skills/monata-env/scripts/execute_monata_env_runbook.py" in live_install
    assert live_install.index("plan_monata_env.py") < live_install.index("execute_monata_env_runbook.py")
    assert "--step check_channel --step install --step smoke --step audit" in live_install
    assert "--allow-confirmation-required" in live_install
    assert "/tmp/skill-home/monata-env-session/monata-env-install-manifest.json" in live_install
    assert data["container"]["host_pixi_root"] == str(host_pixi_root.resolve())
    assert data["container"]["live_install_smoke_command"] == live_install


def test_plan_decisions_can_emit_isolated_upstream_installed_command(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    image = tmp_path / "monata-env-python.sif"
    host_pixi_root = tmp_path / "host-pixi"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    write_channel_artifacts(output_dir, ["ngspice", "openvaf-r", "klayout", "xschem"])
    image.write_text("sif", encoding="utf-8")
    (host_pixi_root / "bin").mkdir(parents=True)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            "--container-image",
            image,
            "--host-pixi-root",
            host_pixi_root,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    decisions = {decision["id"]: decision for decision in data["decisions"]}
    singularity = {option["id"]: option for option in decisions["test_isolation"]["options"]}["singularity"]
    upstream = singularity["commands"]["install_smoke_upstream"]
    assert f"--bind {klayout_source.resolve()}:/mnt/sources/klayout:ro" in upstream
    assert f"--bind {xschem_source.resolve()}:/mnt/sources/xschem:ro" in upstream
    assert "--local-source klayout=/mnt/sources/klayout" in upstream
    assert "--local-source xschem=/mnt/sources/xschem" in upstream
    assert "--step check_channel --step install --step smoke --step upstream_installed_tests --step audit" in upstream
    assert data["container"]["live_install_smoke_upstream_command"] == upstream


def test_plan_decisions_recommend_local_sources_and_basic_upstream_profile(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--local-source",
            f"klayout={klayout_source}",
            "--local-source",
            f"xschem={xschem_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    decisions = {decision["id"]: decision for decision in data["decisions"]}
    assert decisions["source_policy"]["default"] == "local_sources"
    source_options = {option["id"]: option for option in decisions["source_policy"]["options"]}
    assert source_options["local_sources"]["recommended"] is True
    assert source_options["local_sources"]["sources"] == {
        "klayout": str(klayout_source.resolve()),
        "xschem": str(xschem_source.resolve()),
    }
    assert decisions["upstream_test_profile"]["default"] == "basic"
    profile_options = {option["id"]: option for option in decisions["upstream_test_profile"]["options"]}
    assert profile_options["basic"]["recommended"] is True
    assert profile_options["full"]["recommended"] is False
    assert profile_options["skip"]["recommended"] is False


def test_smoke_script_returns_structured_missing_tool_status(tmp_path):
    empty_bin = tmp_path / "bin"
    empty_bin.mkdir()
    env = os.environ.copy()
    env["PATH"] = str(empty_bin)

    result = run([sys.executable, SMOKE_SCRIPT, "--format", "json", "--tool", "ngspice"], env=env)

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["tools"]["ngspice"]["ok"] is False
    assert data["tools"]["ngspice"]["reason"] == "missing"


def test_smoke_script_runs_klayout_ruby_and_python_batch_scripts(tmp_path):
    bin_dir = tmp_path / "bin"
    work_dir = tmp_path / "work"
    fake_klayout = bin_dir / "klayout"
    write_executable(
        fake_klayout,
        f"#!{sys.executable}\n"
        "import re, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "if '-v' in args:\n"
        "    print('KLayout 0.30.9')\n"
        "    raise SystemExit(0)\n"
        "script = Path(args[args.index('-r') + 1])\n"
        "text = script.read_text()\n"
        "match = re.search(r\"layout\\.write\\(['\\\"]([^'\\\"]+)\", text)\n"
        "if not match:\n"
        "    print('missing layout.write path')\n"
        "    raise SystemExit(2)\n"
        "Path(match.group(1)).write_bytes(b'gds')\n"
        "print('wrote ' + match.group(1))\n",
    )
    env = {**os.environ, "PATH": str(bin_dir)}

    result = run(
        [
            sys.executable,
            SMOKE_SCRIPT,
            "--tool",
            "klayout",
            "--work-dir",
            work_dir,
            "--format",
            "json",
        ],
        env=env,
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    checks = data["tools"]["klayout"]["checks"]
    scripts = [" ".join(item["command"]) for item in checks if "-r" in item["command"]]
    assert any("klayout-smoke.rb" in script for script in scripts)
    assert any("klayout-python-smoke.py" in script for script in scripts)
    assert (work_dir / "klayout-smoke.gds").exists()
    assert (work_dir / "klayout-python-smoke.gds").exists()


def test_upstream_script_returns_structured_missing_source_status(tmp_path):
    missing = tmp_path / "missing-klayout"

    result = run([sys.executable, UPSTREAM_SCRIPT, "--format", "json", "--klayout-source", missing])

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert data["profiles"]["klayout"]["ok"] is False
    assert data["profiles"]["klayout"]["reason"] == "source-missing"
    assert data["profiles"]["klayout"]["source"] == str(missing.resolve())


def test_upstream_script_uses_env_prefix_tclsh_for_full_xschem_profile(tmp_path):
    source = tmp_path / "xschem"
    tests_dir = source / "tests"
    library_dir = source / "xschem_library"
    fake_bin = tmp_path / "bin"
    env_prefix = tmp_path / "monata-env"
    tests_dir.mkdir(parents=True)
    library_dir.mkdir()
    fake_bin.mkdir()
    (env_prefix / "bin").mkdir(parents=True)
    (tests_dir / "run_regression.tcl").write_text("puts ok\n", encoding="utf-8")
    (library_dir / "README").write_text("test library\n", encoding="utf-8")

    xschem = env_prefix / "bin" / "xschem"
    xschem.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    xschem.chmod(0o755)
    tclsh = env_prefix / "bin" / "tclsh"
    tclsh.write_text("#!/bin/sh\nprintf 'env-prefix-tclsh %s\\n' \"$1\"\nexit 0\n", encoding="utf-8")
    tclsh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    result = run(
        [
            sys.executable,
            UPSTREAM_SCRIPT,
            "--format",
            "json",
            "--xschem-source",
            source,
            "--env-prefix",
            env_prefix,
            "--env-name",
            "test-monata-env",
            "--profile",
            "full",
        ],
        env=env,
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["profiles"]["xschem"]["ok"] is True
    assert data["profiles"]["xschem"]["checks"][-1]["command"][0] == str(tclsh.resolve())


def test_upstream_script_splits_full_xschem_profile_into_basic_and_regression_checks(tmp_path):
    source = tmp_path / "xschem"
    tests_dir = source / "tests"
    library_dir = source / "xschem_library"
    fake_bin = tmp_path / "bin"
    env_prefix = tmp_path / "monata-env"
    tests_dir.mkdir(parents=True)
    library_dir.mkdir()
    fake_bin.mkdir()
    (env_prefix / "bin").mkdir(parents=True)
    (tests_dir / "run_regression.tcl").write_text("puts ok\n", encoding="utf-8")
    (library_dir / "README").write_text("test library\n", encoding="utf-8")

    xschem = env_prefix / "bin" / "xschem"
    xschem.write_text(
        "#!/bin/sh\n"
        "mkdir -p \"$(dirname \"$1\")\"\n"
        "printf 'schematic\\n' > \"$1\"\n"
        "printf 'basic-create-save-ok\\n'\n",
        encoding="utf-8",
    )
    xschem.chmod(0o755)
    tclsh = env_prefix / "bin" / "tclsh"
    tclsh.write_text("#!/bin/sh\nprintf 'full-regression-ok %s\\n' \"$1\"\nexit 0\n", encoding="utf-8")
    tclsh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    result = run(
        [
            sys.executable,
            UPSTREAM_SCRIPT,
            "--format",
            "json",
            "--xschem-source",
            source,
            "--env-prefix",
            env_prefix,
            "--env-name",
            "test-monata-env",
            "--profile",
            "full",
        ],
        env=env,
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    checks = data["profiles"]["xschem"]["checks"]
    assert [check["id"] for check in checks] == ["xschem-basic-create-save", "xschem-full-regression"]
    assert checks[0]["command"][0] == str(xschem.resolve())
    assert checks[0]["output_size"] > 0
    assert checks[1]["command"][0] == str(tclsh.resolve())
    assert "full-regression-ok" in checks[1]["output"]


def test_upstream_script_can_reuse_kept_work_dir_for_xschem_reruns(tmp_path):
    source = tmp_path / "xschem"
    tests_dir = source / "tests"
    library_dir = source / "xschem_library"
    env_prefix = tmp_path / "monata-env"
    work_dir = tmp_path / "upstream-work"
    tests_dir.mkdir(parents=True)
    library_dir.mkdir()
    (env_prefix / "bin").mkdir(parents=True)
    (tests_dir / "run_regression.tcl").write_text("puts ok\n", encoding="utf-8")
    (library_dir / "README").write_text("test library\n", encoding="utf-8")

    xschem = env_prefix / "bin" / "xschem"
    xschem.write_text(
        "#!/bin/sh\n"
        "mkdir -p \"$(dirname \"$1\")\"\n"
        "printf 'schematic\\n' > \"$1\"\n"
        "printf 'create-save-ok\\n'\n",
        encoding="utf-8",
    )
    xschem.chmod(0o755)

    base_command = [
        sys.executable,
        UPSTREAM_SCRIPT,
        "--format",
        "json",
        "--xschem-source",
        source,
        "--env-prefix",
        env_prefix,
        "--env-name",
        "test-monata-env",
        "--work-dir",
        work_dir,
        "--keep-work-dir",
    ]

    first = run(base_command)
    stale = work_dir / "xschem-upstream" / "stale.txt"
    stale.write_text("stale\n", encoding="utf-8")
    second = run(base_command)

    assert first.returncode == 0, first.stdout
    assert second.returncode == 0, second.stdout
    assert not stale.exists()
    data = json.loads(second.stdout)
    assert data["profiles"]["xschem"]["checks"][0]["output_size"] > 0


def test_upstream_script_reports_structured_timeout_for_full_xschem_profile(tmp_path):
    source = tmp_path / "xschem"
    tests_dir = source / "tests"
    library_dir = source / "xschem_library"
    fake_bin = tmp_path / "bin"
    env_prefix = tmp_path / "monata-env"
    tests_dir.mkdir(parents=True)
    library_dir.mkdir()
    fake_bin.mkdir()
    (env_prefix / "bin").mkdir(parents=True)
    (tests_dir / "run_regression.tcl").write_text("puts ok\n", encoding="utf-8")
    (library_dir / "README").write_text("test library\n", encoding="utf-8")

    xschem = env_prefix / "bin" / "xschem"
    xschem.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    xschem.chmod(0o755)
    tclsh = env_prefix / "bin" / "tclsh"
    tclsh.write_text("#!/bin/sh\n/bin/sleep 5\n", encoding="utf-8")
    tclsh.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(fake_bin)
    result = run(
        [
            sys.executable,
            UPSTREAM_SCRIPT,
            "--format",
            "json",
            "--xschem-source",
            source,
            "--env-prefix",
            env_prefix,
            "--env-name",
            "test-monata-env",
            "--profile",
            "full",
            "--timeout",
            "1",
        ],
        env=env,
    )

    assert result.returncode == 1, result.stdout
    data = json.loads(result.stdout)
    xschem_result = data["profiles"]["xschem"]
    assert xschem_result["reason"] == "command-timeout"
    assert [check["id"] for check in xschem_result["checks"]] == [
        "xschem-basic-create-save",
        "xschem-full-regression",
    ]
    assert xschem_result["checks"][0]["returncode"] == 0
    assert xschem_result["checks"][1]["returncode"] == 124
    assert "timed out after 1s" in xschem_result["checks"][1]["output"]


def test_plan_can_write_manifest_seed(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    write_monata_workspace(workspace)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--write-manifest",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    manifest = output_dir / "monata-env-install-manifest.json"
    assert manifest.exists()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["plan"]["mode"] == "ai-native-session"
    assert data["execution"]["commands_run"] == []
    assert data["verification"]["smoke"] is None
    assert data["verification"]["upstream_installed"] is None


def test_plan_refuses_to_overwrite_manifest_with_execution_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    manifest = output_dir / "monata-env-install-manifest.json"
    write_monata_workspace(workspace)
    write_auditable_manifest(manifest)
    original = json.loads(manifest.read_text(encoding="utf-8"))

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--write-manifest",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 1
    assert "Refusing to overwrite existing manifest with recorded execution evidence" in result.stdout
    assert json.loads(manifest.read_text(encoding="utf-8")) == original


def test_plan_can_explicitly_overwrite_existing_manifest_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    manifest = output_dir / "monata-env-install-manifest.json"
    write_monata_workspace(workspace)
    write_auditable_manifest(manifest)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--write-manifest",
            "--overwrite-manifest",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["execution"]["commands_run"] == []
    assert data["execution"]["artifacts"] == []
    assert data["verification"]["smoke"] is None


def test_execute_runbook_captures_stdout_and_records_verification(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    plan_path = tmp_path / "plan.json"
    smoke_json = tmp_path / "channel" / "smoke.json"
    smoke_err = tmp_path / "channel" / "smoke.err"
    payload = {"ok": True, "tools": {"ngspice": {"ok": True}}}
    write_manifest_seed(manifest)
    command = [
        sys.executable,
        "-c",
        "import json; print(json.dumps({'ok': True, 'tools': {'ngspice': {'ok': True}}}))",
    ]
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "smoke",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": command,
                        "stdout_path": str(smoke_json),
                        "stderr_path": str(smoke_err),
                        "record_after": {
                            "returncode_var": "SMOKE_RC",
                            "command": [
                                sys.executable,
                                str(RECORD_SCRIPT),
                                "--manifest",
                                str(manifest),
                                "--command-kind",
                                "smoke",
                                "--command",
                                "python smoke",
                                "--returncode",
                                "$SMOKE_RC",
                                "--stdout-file",
                                str(smoke_json),
                                "--stderr-file",
                                str(smoke_err),
                                "--verification",
                                f"smoke={smoke_json}",
                            ],
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["ok"] is True
    assert summary["steps"][0]["id"] == "smoke"
    assert summary["steps"][0]["returncode"] == 0
    assert summary["steps"][0]["record_returncode"] == 0
    assert smoke_json.exists()
    assert smoke_err.exists()
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data["verification"]["smoke"] == payload
    assert manifest_data["execution"]["commands_run"][0]["returncode"] == 0
    assert manifest_data["execution"]["commands_run"][0]["stderr_file"] == str(smoke_err.resolve())


def test_execute_runbook_writes_running_and_final_step_status(tmp_path):
    plan_path = tmp_path / "plan.json"
    status_path = tmp_path / "install.status.json"
    command = [
        sys.executable,
        "-c",
        (
            "import json; "
            "from pathlib import Path; "
            f"p=Path({str(status_path)!r}); "
            "d=json.loads(p.read_text()); "
            "assert d['status'] == 'running'; "
            "assert d['id'] == 'install'; "
            "print('saw-running')"
        ),
    ]
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "install",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": command,
                        "status_path": str(status_path),
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["steps"][0]["status_path"] == str(status_path.resolve())
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["id"] == "install"
    assert status["status"] == "executed"
    assert status["returncode"] == 0
    assert status["record_returncode"] is None


def test_execute_runbook_requires_confirmation_for_mutating_steps(tmp_path):
    plan_path = tmp_path / "plan.json"
    marker = tmp_path / "mutated.txt"
    command = [sys.executable, "-c", f"from pathlib import Path; Path({str(marker)!r}).write_text('ran')"]
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "install",
                        "recommended": True,
                        "requires_confirmation": True,
                        "command": command,
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    skipped = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert skipped.returncode == 0, skipped.stdout
    skipped_summary = json.loads(skipped.stdout)
    assert skipped_summary["steps"][0]["status"] == "skipped"
    assert skipped_summary["steps"][0]["reason"] == "requires-confirmation"
    assert not marker.exists()

    executed = run(
        [
            sys.executable,
            EXECUTE_SCRIPT,
            "--plan",
            plan_path,
            "--allow-confirmation-required",
            "--format",
            "json",
        ]
    )

    assert executed.returncode == 0, executed.stdout
    executed_summary = json.loads(executed.stdout)
    assert executed_summary["steps"][0]["status"] == "executed"
    assert marker.read_text(encoding="utf-8") == "ran"


def test_execute_runbook_skips_downstream_when_dependency_is_skipped(tmp_path):
    plan_path = tmp_path / "plan.json"
    install_marker = tmp_path / "install.txt"
    smoke_marker = tmp_path / "smoke.txt"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "install",
                        "recommended": True,
                        "requires_confirmation": True,
                        "command": [
                            sys.executable,
                            "-c",
                            f"from pathlib import Path; Path({str(install_marker)!r}).write_text('install')",
                        ],
                    },
                    {
                        "id": "smoke",
                        "recommended": True,
                        "requires_confirmation": False,
                        "depends_on": ["install"],
                        "command": [
                            sys.executable,
                            "-c",
                            f"from pathlib import Path; Path({str(smoke_marker)!r}).write_text('smoke')",
                        ],
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["steps"][0]["status"] == "skipped"
    assert summary["steps"][0]["reason"] == "requires-confirmation"
    assert summary["steps"][1]["status"] == "skipped"
    assert summary["steps"][1]["reason"] == "dependency-skipped"
    assert summary["steps"][1]["dependency"] == "install"
    assert not install_marker.exists()
    assert not smoke_marker.exists()


def test_execute_runbook_suggests_local_sources_after_network_failure(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "build",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            "import sys; print('failed to download source: network timeout', file=sys.stderr); sys.exit(1)",
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    assert summary["ok"] is False
    action = summary["steps"][0]["next_actions"][0]
    assert action["id"] == "provide-local-source"
    assert action["requires_user_input"] is True
    assert "local KLayout/Xschem source checkout" in action["prompt"]
    assert action["evidence"]["step_id"] == "build"
    assert action["decision"]["id"] == "source_fallback"
    assert action["decision"]["default"] == "provide_local_source"
    option_ids = [option["id"] for option in action["decision"]["options"]]
    assert option_ids == ["provide_local_source", "provide_source_archive", "retry_network"]
    assert summary["next_actions"][0]["id"] == "provide-local-source"


def test_network_failure_recovery_replans_with_user_provided_local_sources(tmp_path):
    plan_path = tmp_path / "plan.json"
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "build",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            "import sys; print('failed to download source: network timeout', file=sys.stderr); sys.exit(1)",
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    failure = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert failure.returncode == 1, failure.stdout
    action = json.loads(failure.stdout)["next_actions"][0]
    source_option = {option["id"]: option for option in action["decision"]["options"]}["provide_local_source"]
    replan_args = [
        part.replace("<klayout-source>", str(klayout_source.resolve())).replace(
            "<xschem-source>", str(xschem_source.resolve())
        )
        for part in source_option["replan_arguments"]
    ]
    recovered = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            *replan_args,
            "--format",
            "json",
        ]
    )

    assert recovered.returncode == 0, recovered.stdout
    data = json.loads(recovered.stdout)
    decisions = {decision["id"]: decision for decision in data["decisions"]}
    assert decisions["source_policy"]["default"] == "local_sources"
    build_command = " ".join(data["commands"]["build"])
    assert f"--local-source klayout={klayout_source.resolve()}" in build_command
    assert f"--local-source xschem={xschem_source.resolve()}" in build_command
    upstream_command = " ".join(data["commands"]["upstream_installed_tests"])
    assert f"--klayout-source {klayout_source.resolve()}" in upstream_command
    assert f"--xschem-source {xschem_source.resolve()}" in upstream_command


def test_network_failure_recovery_replans_with_user_provided_source_archives(tmp_path):
    plan_path = tmp_path / "plan.json"
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    klayout_archive = tmp_path / "klayout-v0.30.9.tar.gz"
    xschem_archive = tmp_path / "xschem-3.4.7.tar.gz"
    write_monata_workspace(workspace)
    write_source_archive(klayout_archive, "klayout-0.30.9")
    write_source_archive(xschem_archive, "xschem-3.4.7")
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "build",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            "import sys; print('could not resolve host for source download', file=sys.stderr); sys.exit(1)",
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    failure = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert failure.returncode == 1, failure.stdout
    action = json.loads(failure.stdout)["next_actions"][0]
    archive_option = {option["id"]: option for option in action["decision"]["options"]}["provide_source_archive"]
    replan_args = [
        part.replace("<klayout-archive>", str(klayout_archive.resolve())).replace(
            "<xschem-archive>", str(xschem_archive.resolve())
        )
        for part in archive_option["replan_arguments"]
    ]
    recovered = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            *replan_args,
            "--format",
            "json",
        ]
    )

    assert recovered.returncode == 0, recovered.stdout
    data = json.loads(recovered.stdout)
    archive_question = data["questions"][0]
    assert archive_question["id"] == "local_source_archive_trust"
    assert archive_question["archive_sources"]["klayout"]["path"] == str(klayout_archive.resolve())
    assert archive_question["archive_sources"]["xschem"]["path"] == str(xschem_archive.resolve())
    build_command = " ".join(data["commands"]["build"])
    assert f"--local-source klayout={klayout_archive.resolve()}" in build_command
    assert f"--local-source xschem={xschem_archive.resolve()}" in build_command
    assert "--local-source-ref klayout=v0.30.9" not in build_command
    assert "--local-source-ref xschem=3.4.7" not in build_command
    assert data["commands"]["upstream_installed_tests"] == []


def test_execute_runbook_suggests_helper_resolution_when_helper_script_is_missing(tmp_path):
    plan_path = tmp_path / "plan.json"
    missing_helper = tmp_path / "missing-rattler-channel.py"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "check_channel",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [sys.executable, str(missing_helper), "check-channel"],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    action = summary["steps"][0]["next_actions"][0]
    assert action["id"] == "resolve-conda-build-helper"
    assert action["requires_user_input"] is False
    assert "plan_monata_env.py --conda-build-helper" in action["command"]
    assert summary["next_actions"][0]["id"] == "resolve-conda-build-helper"


def test_execute_runbook_suggests_worktree_for_source_ref_mismatch(tmp_path):
    plan_path = tmp_path / "plan.json"
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    klayout_source = tmp_path / "klayout"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "build",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            "import sys; print('local source does not match required ref v0.30.9', file=sys.stderr); sys.exit(1)",
                            "--local-source",
                            f"klayout={klayout_source.resolve()}",
                            "--local-source-ref",
                            "klayout=v0.30.9",
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    action = summary["steps"][0]["next_actions"][0]
    assert action["id"] == "create-versioned-source-worktree"
    assert action["requires_user_input"] is True
    assert "detached worktree" in action["prompt"]
    assert action["evidence"]["step_id"] == "build"
    assert action["decision"]["id"] == "local_source_ref_repair"
    assert action["decision"]["default"] == "create_detached_worktree"
    assert [option["id"] for option in action["decision"]["options"]] == [
        "create_detached_worktree",
        "provide_corrected_source",
        "provide_source_archive",
    ]
    source_option = {option["id"]: option for option in action["decision"]["options"]}["create_detached_worktree"]
    worktree_command = source_option["worktree_commands"]["klayout"]
    assert worktree_command[:5] == ["git", "-C", str(klayout_source.resolve()), "worktree", "add"]
    assert "--detach" in worktree_command
    assert worktree_command[-1] == "v0.30.9"

    worktree_result = run(worktree_command)

    assert worktree_result.returncode == 0, worktree_result.stdout
    replan_args = source_option["replan_arguments"]
    recovered = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--session-dir",
            session_dir,
            *replan_args,
            "--format",
            "json",
        ]
    )

    assert recovered.returncode == 0, recovered.stdout
    data = json.loads(recovered.stdout)
    assert data["local_sources"]["klayout"]["status"] == "ok"
    assert data["questions"] == []
    build_command = " ".join(data["commands"]["build"])
    assert "--local-source klayout=" in build_command
    assert "--local-source-ref klayout=v0.30.9" in build_command


def test_execute_runbook_suggests_tool_inspection_for_smoke_failure(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "smoke",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            "import sys; print('{\"ok\": false, \"tools\": {\"xschem\": {\"reason\": \"missing\"}}}'); sys.exit(1)",
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    action = summary["steps"][0]["next_actions"][0]
    assert action["id"] == "inspect-installed-tools"
    assert action["requires_user_input"] is False
    assert "smoke_monata_env_tools.py" in action["command"]


def test_execute_runbook_preserves_json_next_actions_from_audit_failure(tmp_path):
    plan_path = tmp_path / "plan.json"
    audit_json = tmp_path / "audit.json"
    audit_payload = {
        "ok": False,
        "status": "blocked",
        "next_actions": [
            {
                "id": "repair-live-monata-env",
                "title": "Repair the current pixi global monata-env state",
                "requires_user_input": True,
                "command": "pixi global list --json",
                "prompt": "Audit found a live monata-env mismatch.",
            }
        ],
    }
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "audit",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            f"import json, sys; print(json.dumps({audit_payload!r})); sys.exit(1)",
                        ],
                        "stdout_path": str(audit_json),
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    assert summary["steps"][0]["next_actions"][0]["id"] == "repair-live-monata-env"
    assert summary["steps"][0]["next_actions"][0]["prompt"] == "Audit found a live monata-env mismatch."
    assert summary["steps"][0]["stdout_path"] == str(audit_json.resolve())
    assert summary["next_actions"][0]["id"] == "repair-live-monata-env"


def test_execute_runbook_suggests_upstream_test_dependency_for_tclsh_missing(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "upstream_installed_tests",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            (
                                "import json, sys; "
                                "print(json.dumps({'ok': False, 'profiles': "
                                "{'xschem': {'reason': 'tclsh-missing'}}})); "
                                "sys.exit(1)"
                            ),
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    action_ids = [action["id"] for action in summary["steps"][0]["next_actions"]]
    assert action_ids[:2] == ["install-upstream-test-dependency", "use-basic-upstream-profile"]
    assert summary["steps"][0]["next_actions"][0]["requires_user_input"] is True
    assert summary["steps"][0]["next_actions"][1]["requires_user_input"] is False
    assert "tclsh" in summary["steps"][0]["next_actions"][0]["prompt"]
    assert "--upstream-profile basic" in summary["steps"][0]["next_actions"][1]["command"]


def test_execute_runbook_suggests_full_regression_recovery_after_xschem_timeout(tmp_path):
    plan_path = tmp_path / "plan.json"
    upstream_output = tmp_path / "fake-upstream-output.py"
    upstream_payload = {
        "ok": False,
        "profiles": {
            "xschem": {
                "ok": False,
                "reason": "command-timeout",
                "checks": [
                    {"id": "xschem-basic-create-save", "returncode": 0, "output": "basic ok"},
                    {
                        "id": "xschem-full-regression",
                        "returncode": 124,
                        "output": "Start source create_save.tcl\n\ntimed out after 300s\n",
                    },
                ],
            }
        },
    }
    upstream_output.write_text(
        "import json, sys\n"
        f"print(json.dumps({upstream_payload!r}))\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    original_command = [
        sys.executable,
        str(UPSTREAM_SCRIPT),
        "--format",
        "json",
        "--profile",
        "full",
        "--timeout",
        "300",
        "--work-dir",
        "/tmp/monata-env-upstream-work",
        "--keep-work-dir",
        "--klayout-source",
        "/src/klayout",
        "--xschem-source",
        "/src/xschem",
    ]
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "upstream_installed_tests",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [sys.executable, str(upstream_output)],
                        "original_command": original_command,
                        "stdout_path": str(tmp_path / "upstream.json"),
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    action_ids = [action["id"] for action in summary["steps"][0]["next_actions"]]
    assert action_ids[:2] == ["inspect-xschem-full-regression-timeout", "use-basic-upstream-profile"]
    assert summary["steps"][0]["next_actions"][0]["requires_user_input"] is False
    assert "xschem-full-regression" in summary["steps"][0]["next_actions"][0]["prompt"]
    rerun_command = summary["steps"][0]["next_actions"][0]["command"]
    assert "test_monata_env_upstream.py" in rerun_command
    assert "--profile full" in rerun_command
    assert "--timeout 900" in rerun_command
    assert "--work-dir /tmp/monata-env-upstream-work" in rerun_command
    assert "--keep-work-dir" in rerun_command
    assert "--upstream-profile basic" in summary["steps"][0]["next_actions"][1]["command"]


def test_execute_runbook_times_out_step_and_suggests_timeout_recovery(tmp_path):
    plan_path = tmp_path / "plan.json"
    status_path = tmp_path / "install.status.json"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "install",
                        "recommended": True,
                        "requires_confirmation": False,
                        "timeout_seconds": 1,
                        "status_path": str(status_path),
                        "command": [
                            sys.executable,
                            "-c",
                            "import time; time.sleep(10)",
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = run([sys.executable, EXECUTE_SCRIPT, "--plan", plan_path, "--format", "json"])

    assert result.returncode == 1, result.stdout
    summary = json.loads(result.stdout)
    step = summary["steps"][0]
    assert step["status"] == "executed"
    assert step["returncode"] == 124
    assert "timed out after 1s" in step["stderr"]
    assert step["next_actions"][0]["id"] == "inspect-timeout-or-cache"
    assert step["next_actions"][0]["requires_user_input"] is True
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["status"] == "executed"
    assert status["next_actions"][0]["id"] == "inspect-timeout-or-cache"


def test_record_manifest_appends_command_and_verification_payload(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    smoke_output = tmp_path / "smoke.json"
    payload = {"ok": True, "tools": {"ngspice": {"ok": True}}}
    write_manifest_seed(manifest)
    smoke_output.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    result = run(
        [
            sys.executable,
            RECORD_SCRIPT,
            "--manifest",
            manifest,
            "--command-kind",
            "smoke",
            "--command",
            "python scripts/smoke_monata_env_tools.py --format json",
            "--returncode",
            "0",
            "--stdout-file",
            smoke_output,
            "--verification",
            f"smoke={smoke_output}",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["execution"]["commands_run"] == [
        {
            "kind": "smoke",
            "command": "python scripts/smoke_monata_env_tools.py --format json",
            "returncode": 0,
            "stdout_file": str(smoke_output.resolve()),
        }
    ]
    assert data["verification"]["smoke"] == payload


def test_record_manifest_collects_package_artifacts(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    linux64 = tmp_path / "channel" / "linux-64"
    artifact = linux64 / "klayout-0.30.9-hb0f4dca_0.conda"
    write_manifest_seed(manifest)
    linux64.mkdir(parents=True)
    artifact.write_text("package-bytes", encoding="utf-8")

    result = run(
        [
            sys.executable,
            RECORD_SCRIPT,
            "--manifest",
            manifest,
            "--artifact-dir",
            tmp_path / "channel",
            "--package",
            "klayout",
            "--package",
            "xschem",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["execution"]["artifacts"] == [
        {
            "package": "klayout",
            "path": str(artifact.resolve()),
            "filename": artifact.name,
            "size": len("package-bytes"),
        }
    ]


def test_record_manifest_preserves_failed_command_when_verification_json_is_invalid(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    smoke_output = tmp_path / "broken-smoke.json"
    write_manifest_seed(manifest)
    smoke_output.write_text("traceback, not json\n", encoding="utf-8")

    result = run(
        [
            sys.executable,
            RECORD_SCRIPT,
            "--manifest",
            manifest,
            "--command-kind",
            "smoke",
            "--command",
            "python scripts/smoke_monata_env_tools.py --format json",
            "--returncode",
            "1",
            "--stdout-file",
            smoke_output,
            "--verification",
            f"smoke={smoke_output}",
        ]
    )

    assert result.returncode == 1
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["execution"]["commands_run"][0]["returncode"] == 1
    assert data["execution"]["commands_run"][0]["stdout_file"] == str(smoke_output.resolve())
    assert data["verification"]["smoke"]["ok"] is False
    assert data["verification"]["smoke"]["reason"] == "invalid-json"
    assert data["verification"]["smoke"]["path"] == str(smoke_output.resolve())


def test_audit_manifest_reports_ready_after_successful_smoke(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    write_auditable_manifest(manifest)

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--format", "json"])

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    requirements = {item["id"]: item for item in data["requirements"]}
    assert data["ok"] is True
    assert data["status"] == "ready"
    assert data["summary"]["env_name"] == "monata-env"
    assert requirements["expected-tool-plan"]["ok"] is True
    assert requirements["no-monata-or-techlibs"]["ok"] is True
    assert requirements["install-command-succeeded"]["ok"] is True
    assert requirements["installed-tool-smoke"]["ok"] is True
    assert data["next_actions"] == []


def test_audit_manifest_reports_evidence_for_user_facing_status(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    tools = ["ngspice", "openvaf-r", "klayout", "xschem"]
    artifacts = [
        {
            "package": tool,
            "path": str((tmp_path / "channel" / "linux-64" / f"{tool}-1.0-0.conda").resolve()),
            "filename": f"{tool}-1.0-0.conda",
            "size": 123,
        }
        for tool in tools
    ]
    write_auditable_manifest(manifest, artifacts=artifacts)

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--format", "json"])

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    evidence = data["evidence"]
    assert evidence["commands"]["by_kind"]["install"]["ok"] is True
    assert evidence["commands"]["by_kind"]["smoke"]["returncode"] == 0
    assert evidence["artifacts"]["present_packages"] == tools
    assert evidence["artifacts"]["missing_packages"] == []
    assert evidence["verification"]["smoke"] == "passed"
    assert evidence["verification"]["upstream_installed"] == "not-requested"


def test_audit_manifest_can_require_package_artifacts(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    write_auditable_manifest(manifest)

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--require-artifacts", "--format", "json"])

    assert result.returncode == 1
    data = json.loads(result.stdout)
    requirements = {item["id"]: item for item in data["requirements"]}
    assert data["status"] == "blocked"
    assert requirements["package-artifacts-recorded"]["ok"] is False
    assert requirements["package-artifacts-recorded"]["missing"] == ["ngspice", "openvaf-r", "klayout", "xschem"]
    action = data["next_actions"][0]
    assert action["id"] == "record-package-artifacts"
    assert "execute_monata_env_runbook.py" in action["command"]
    assert "--step check_channel" in action["command"]
    assert action["evidence"]["missing_packages"] == ["ngspice", "openvaf-r", "klayout", "xschem"]
    assert action["decision"]["id"] == "artifact_evidence_repair"
    assert action["decision"]["default"] == "record_existing_channel"


def test_plan_final_audit_requires_package_artifact_evidence(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    write_monata_workspace(workspace)

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    runbook = {step["id"]: step for step in data["runbook"]}
    assert "--require-artifacts" in runbook["audit"]["command"]


def test_audit_summary_prints_user_facing_status_report(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    tools = ["ngspice", "openvaf-r", "klayout", "xschem"]
    artifacts = [
        {
            "package": tool,
            "path": str((tmp_path / "channel" / "linux-64" / f"{tool}-1.0-0.conda").resolve()),
            "filename": f"{tool}-1.0-0.conda",
            "size": 123,
        }
        for tool in tools
    ]
    write_auditable_manifest(manifest, artifacts=artifacts)

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--format", "summary"])

    assert result.returncode == 0, result.stdout
    assert "status: ready" in result.stdout
    assert "env_name: monata-env" in result.stdout
    assert "artifacts: ngspice openvaf-r klayout xschem" in result.stdout
    assert "verification: smoke=passed upstream_installed=not-requested live_state=not-checked" in result.stdout
    assert "next_actions: none" in result.stdout


def test_audit_manifest_blocks_monata_package_or_techlib_bootstrap(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    tools = ["ngspice", "openvaf-r", "klayout", "xschem"]
    write_auditable_manifest(
        manifest,
        plan={
            "mode": "ai-native-session",
            "env_name": "monata-env",
            "packages": [*tools, "monata"],
            "commands": {
                "install": ["pixi", "global", "install", "--environment", "monata-env", "monata"],
                "techlib": ["pixi", "run", "python", "bootstrap_monata_techlibs.py"],
            },
        },
    )

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--format", "json"])

    assert result.returncode == 1, result.stdout
    data = json.loads(result.stdout)
    requirements = {item["id"]: item for item in data["requirements"]}
    assert data["ok"] is False
    assert data["status"] == "blocked"
    assert requirements["no-monata-or-techlibs"]["ok"] is False
    assert "monata" in requirements["no-monata-or-techlibs"]["problems"]
    action_ids = [item["id"] for item in data["next_actions"]]
    assert action_ids[0] == "remove-monata-techlib-bootstrap"


def test_audit_live_state_reports_ready_when_pixi_env_matches_manifest(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    bin_dir = tmp_path / "bin"
    tools = ["ngspice", "openvaf-r", "klayout", "xschem"]
    write_auditable_manifest(manifest)
    for tool in tools:
        write_executable(bin_dir / tool)
    pixi_payload = [
        {
            "name": "monata-env",
            "dependencies": [{"name": tool, "version": "1.0"} for tool in tools],
            "exposed": [{"exposed_name": tool, "executable": tool} for tool in tools],
        }
    ]
    write_executable(
        bin_dir / "pixi",
        f"#!{sys.executable}\n"
        "import json\n"
        f"print(json.dumps({pixi_payload!r}))\n",
    )
    env = {**os.environ, "PATH": str(bin_dir)}

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--check-live", "--format", "json"], env=env)

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    requirements = {item["id"]: item for item in data["requirements"]}
    assert data["ok"] is True
    assert data["status"] == "ready"
    assert data["summary"]["live_state"] == "matched"
    assert requirements["live-monata-env"]["ok"] is True
    assert requirements["live-monata-env"]["packages"] == tools
    assert requirements["live-monata-env"]["exposed"] == tools
    assert set(requirements["live-monata-env"]["command_paths"]) == set(tools)


def test_audit_live_state_blocks_missing_exposed_command_or_monata_package(tmp_path):
    manifest = tmp_path / "channel" / "monata-env-install-manifest.json"
    bin_dir = tmp_path / "bin"
    tools = ["ngspice", "openvaf-r", "klayout", "xschem"]
    write_auditable_manifest(manifest)
    for tool in tools[:-1]:
        write_executable(bin_dir / tool)
    pixi_payload = [
        {
            "name": "monata-env",
            "dependencies": [{"name": tool, "version": "1.0"} for tool in [*tools, "monata"]],
            "exposed": [{"exposed_name": tool, "executable": tool} for tool in tools[:-1]],
        }
    ]
    write_executable(
        bin_dir / "pixi",
        f"#!{sys.executable}\n"
        "import json\n"
        f"print(json.dumps({pixi_payload!r}))\n",
    )
    env = {**os.environ, "PATH": str(bin_dir)}

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--check-live", "--format", "json"], env=env)

    assert result.returncode == 1, result.stdout
    data = json.loads(result.stdout)
    requirements = {item["id"]: item for item in data["requirements"]}
    assert data["ok"] is False
    assert data["status"] == "blocked"
    assert data["summary"]["live_state"] == "mismatch"
    live = requirements["live-monata-env"]
    assert live["ok"] is False
    assert live["missing_commands"] == ["xschem"]
    assert live["missing_exposures"] == ["xschem"]
    assert live["forbidden_packages"] == ["monata"]
    assert data["next_actions"][0]["id"] == "repair-live-monata-env"


def test_rattler_local_source_ref_rejects_mismatched_checkout(tmp_path):
    source = tmp_path / "klayout"
    channel = tmp_path / "channel"
    git_repo_with_tagged_parent(source, "v0.30.9")
    env = os.environ.copy()
    env["CONDA_BUILD_OUTPUT_DIR"] = str(channel)

    result = run(
        [
            sys.executable,
            RATTLER_SCRIPT,
            "build",
            "--recipe-set",
            "circuit-toolchain",
            "--package",
            "klayout",
            "--local-source",
            f"klayout={source}",
            "--local-source-ref",
            "klayout=v0.30.9",
            "--dry-run",
        ],
        env=env,
    )

    assert result.returncode != 0
    assert "does not match required ref" in result.stdout


def test_rattler_local_source_archive_dry_run_uses_extracted_source_path(tmp_path):
    archive = tmp_path / "klayout-v0.30.9.tar.gz"
    channel = tmp_path / "channel"
    write_source_archive(archive, "klayout-0.30.9")

    result = run(
        [
            sys.executable,
            RATTLER_SCRIPT,
            "build",
            "--recipe-set",
            "circuit-toolchain",
            "--package",
            "klayout",
            "--local-source",
            f"klayout={archive}",
            "--output-dir",
            channel,
            "--dry-run",
        ]
    )

    assert result.returncode == 0, result.stdout
    assert "# local-source-archive klayout=" in result.stdout
    assert "klayout-v0.30.9.tar.gz" in result.stdout
    assert "+ rattler-build build" in result.stdout


def test_rattler_local_source_archive_rejects_git_ref_validation(tmp_path):
    archive = tmp_path / "klayout-v0.30.9.tar.gz"
    channel = tmp_path / "channel"
    write_source_archive(archive, "klayout-0.30.9")

    result = run(
        [
            sys.executable,
            RATTLER_SCRIPT,
            "build",
            "--recipe-set",
            "circuit-toolchain",
            "--package",
            "klayout",
            "--local-source",
            f"klayout={archive}",
            "--local-source-ref",
            "klayout=v0.30.9",
            "--output-dir",
            channel,
            "--dry-run",
        ]
    )

    assert result.returncode != 0
    assert "cannot validate git ref v0.30.9 for local source archive" in result.stdout
