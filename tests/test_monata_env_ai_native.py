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
    assert build_step["recommended"] is True
    assert build_step["command"] == data["commands"]["build"]
    assert build_step["record_after"]["returncode_var"] == "BUILD_RC"
    build_record = " ".join(build_step["record_after"]["command"])
    assert "record_monata_env_session.py" in build_record
    assert "--command-kind build" in build_record
    assert f"--artifact-dir {output_dir.resolve()}" in build_record
    assert "--package ngspice" in build_record
    assert "--package openvaf-r" in build_record
    assert "--package klayout" in build_record
    assert "--package xschem" in build_record

    install_step = runbook["install"]
    assert install_step["depends_on"] == ["build"]
    assert install_step["record_after"]["returncode_var"] == "INSTALL_RC"
    assert "--command-kind install" in " ".join(install_step["record_after"]["command"])

    smoke_step = runbook["smoke"]
    assert smoke_step["depends_on"] == ["install"]
    smoke_json = output_dir.resolve() / "monata-env-smoke.json"
    assert smoke_step["stdout_path"] == str(smoke_json)
    assert smoke_step["record_after"]["returncode_var"] == "SMOKE_RC"
    smoke_record = " ".join(smoke_step["record_after"]["command"])
    assert "--command-kind smoke" in smoke_record
    assert f"--stdout-file {smoke_json}" in smoke_record
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
    assert "scripts/skill_container.py" in isolation_options["singularity"]["command"]
    assert "/mnt/skills/scripts/plan_monata_env.py" in isolation_options["singularity"]["command"]
    assert "/mnt/skills/plugins/monata-env" not in isolation_options["singularity"]["command"]
    assert decisions["upstream_test_profile"]["default"] == "skip"


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
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert manifest_data["verification"]["smoke"] == payload
    assert manifest_data["execution"]["commands_run"][0]["returncode"] == 0


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
