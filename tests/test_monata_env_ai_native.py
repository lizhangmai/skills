import json
import os
import subprocess
import sys
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
    assert "--step install --step smoke --step upstream_installed_tests" in upstream


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
    assert "--step install --step smoke" in live_install
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
    assert "--step install --step smoke --step upstream_installed_tests" in upstream
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

    xschem = fake_bin / "xschem"
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
            "--profile",
            "full",
        ],
        env=env,
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["profiles"]["xschem"]["ok"] is True
    assert data["profiles"]["xschem"]["checks"][0]["command"][0] == str(tclsh.resolve())


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

    xschem = fake_bin / "xschem"
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
    assert xschem_result["checks"][0]["returncode"] == 124
    assert "timed out after 1s" in xschem_result["checks"][0]["output"]


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
    assert summary["next_actions"][0]["id"] == "provide-local-source"


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


def test_execute_runbook_times_out_step_and_suggests_timeout_recovery(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "install",
                        "recommended": True,
                        "requires_confirmation": False,
                        "timeout_seconds": 1,
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
