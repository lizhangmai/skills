from monata_env_helpers import *


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


def test_plan_reports_missing_submodules_for_local_git_source(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    klayout_source = tmp_path / "klayout"
    write_monata_workspace(workspace)
    git_repo_with_uninitialized_submodule(klayout_source, "v0.30.9", tmp_path / "submodule-source")

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
    assert data["local_sources"]["klayout"]["status"] == "submodule-missing"
    assert data["local_sources"]["klayout"]["missing_submodules"] == ["deps/model"]
    assert data["questions"][0]["id"] == "local_source_repair"
    assert data["questions"][0]["problem_sources"]["klayout"]["status"] == "submodule-missing"


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


def test_plan_rerun_builds_only_missing_packages_with_skip_existing(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    write_monata_workspace(workspace)
    write_channel_artifacts(output_dir, ["ngspice", "openvaf-r", "xschem"])

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
    assert data["channel"]["missing"] == ["klayout"]
    assert data["build_packages"] == ["klayout"]
    build = data["commands"]["build"]
    assert build[build.index("--package") + 1] == "klayout"
    assert "--skip-existing" in build
    runbook = {step["id"]: step for step in data["runbook"]}
    assert runbook["build"]["depends_on"] == ["check_channel"]
    assert runbook["install"]["depends_on"] == ["build"]


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


def test_plan_emits_isolated_live_build_upstream_command_with_timeout(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    image = tmp_path / "monata-env-python.sif"
    host_pixi_root = tmp_path / "host-pixi"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    write_channel_artifacts(output_dir, ["ngspice", "openvaf-r"])
    image.write_text("sif", encoding="utf-8")
    (host_pixi_root / "bin").mkdir(parents=True)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")
    run(["git", "-C", klayout_source, "checkout", "--detach", "v0.30.9"])
    run(["git", "-C", xschem_source, "checkout", "--detach", "3.4.7"])

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
            "--live-timeout-seconds",
            "12345",
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
    build_upstream = singularity["commands"]["build_install_smoke_upstream"]
    assert data["build_packages"] == ["klayout", "xschem"]
    assert data["container"]["live_timeout_seconds"] == 12345
    assert data["container"]["live_build_install_smoke_upstream_command"] == build_upstream
    assert data["container"]["cache_strategy"]["state_dir"] == str(session_dir.resolve() / "container-state")
    assert data["container"]["cache_strategy"]["singularity_cache_dir"].endswith("container-state/singularity-cache")
    build_command = " ".join(data["commands"]["build"])
    assert "--package klayout" in build_command
    assert "--package xschem" in build_command
    assert "--local-source-ref klayout=v0.30.9" in build_command
    assert "--local-source-ref xschem=3.4.7" in build_command
    assert f"--state-dir {session_dir.resolve() / 'container-state'}" in build_upstream
    assert "--timeout-seconds 12345" in build_upstream
    assert f"--bind {klayout_source.resolve()}:/mnt/sources/klayout:ro" in build_upstream
    assert f"--bind {xschem_source.resolve()}:/mnt/sources/xschem:ro" in build_upstream
    assert "--local-source klayout=/mnt/sources/klayout" in build_upstream
    assert "--local-source xschem=/mnt/sources/xschem" in build_upstream
    assert "--step check_channel --step build --step install --step smoke --step upstream_installed_tests --step audit" in build_upstream


def test_historical_monata_sim_env_docs_are_marked_superseded():
    docs = [
        REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-06-19-monata-env-design.md",
        REPO_ROOT / "docs" / "superpowers" / "plans" / "2026-06-19-monata-env.md",
    ]
    for path in docs:
        text = path.read_text(encoding="utf-8")
        assert "monata-sim-env" in text
        assert "Historical note" in text
        assert "plugins/monata-env/skills/monata-env/SKILL.md" in text
        assert "active install runbook" in text


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
