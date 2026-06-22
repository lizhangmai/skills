from monata_env_helpers import *


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


def test_execute_runbook_uses_structured_source_download_error(tmp_path):
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
                            (
                                "import json, sys; "
                                "print(json.dumps({'ok': False, 'error': {'code': 'source-download-failed'}})); "
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
    assert summary["steps"][0]["next_actions"][0]["id"] == "provide-local-source"
    assert summary["steps"][0]["next_actions"][0]["evidence"]["error_code"] == "source-download-failed"


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


def test_network_failure_negotiation_replay_generates_replan_args_and_continues_runbook(tmp_path):
    failed_plan = tmp_path / "failed-plan.json"
    failed_summary = tmp_path / "failed-summary.json"
    recovered_plan = tmp_path / "recovered-plan.json"
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    session_dir = tmp_path / "session"
    klayout_source = tmp_path / "klayout"
    xschem_source = tmp_path / "xschem"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v0.30.9")
    git_repo_with_tagged_parent(xschem_source, "3.4.7")
    failed_plan.write_text(
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
                            (
                                "import json, sys; "
                                "print(json.dumps({'ok': False, 'error': {'code': 'source-download-failed'}})); "
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

    failure = run([sys.executable, EXECUTE_SCRIPT, "--plan", failed_plan, "--format", "json"])
    assert failure.returncode == 1, failure.stdout
    failed_summary.write_text(failure.stdout, encoding="utf-8")
    replay = run(
        [
            sys.executable,
            REPLAY_SCRIPT,
            "--summary",
            failed_summary,
            "--action",
            "provide-local-source",
            "--option",
            "provide_local_source",
            "--replace",
            f"<klayout-source>={klayout_source.resolve()}",
            "--replace",
            f"<xschem-source>={xschem_source.resolve()}",
            "--format",
            "json",
        ]
    )

    assert replay.returncode == 0, replay.stdout
    replay_data = json.loads(replay.stdout)
    assert replay_data["action_id"] == "provide-local-source"
    assert replay_data["option_id"] == "provide_local_source"
    replan_args = replay_data["replan_arguments"]
    assert "<klayout-source>" not in replan_args
    assert f"klayout={klayout_source.resolve()}" in replan_args

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
    recovered_plan.write_text(recovered.stdout, encoding="utf-8")

    dry_run = run(
        [
            sys.executable,
            EXECUTE_SCRIPT,
            "--plan",
            recovered_plan,
            "--dry-run",
            "--include-optional",
            "--allow-confirmation-required",
            "--step",
            "build",
            "--step",
            "upstream_installed_tests",
            "--format",
            "json",
        ]
    )

    assert dry_run.returncode == 0, dry_run.stdout
    dry_data = json.loads(dry_run.stdout)
    steps = {step["id"]: step for step in dry_data["steps"]}
    assert steps["build"]["status"] == "dry-run"
    assert steps["upstream_installed_tests"]["status"] == "dry-run"


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


def test_execute_runbook_uses_structured_helper_missing_error(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "check_channel",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [
                            sys.executable,
                            "-c",
                            (
                                "import json, sys; "
                                "print(json.dumps({'ok': False, 'error': {'code': 'conda-build-helper-missing'}})); "
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
    assert summary["steps"][0]["next_actions"][0]["id"] == "resolve-conda-build-helper"
    assert summary["steps"][0]["next_actions"][0]["evidence"]["error_code"] == "conda-build-helper-missing"


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


def test_execute_runbook_uses_structured_source_ref_mismatch_error(tmp_path):
    plan_path = tmp_path / "plan.json"
    klayout_source = tmp_path / "klayout"
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
                            (
                                "import json, sys; "
                                "print(json.dumps({'ok': False, 'error': {'code': 'local-source-ref-mismatch'}})); "
                                "sys.exit(1)"
                            ),
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
    assert action["evidence"]["error_code"] == "local-source-ref-mismatch"
    assert action["decision"]["options"][0]["worktree_commands"]["klayout"][-1] == "v0.30.9"


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


def test_execute_runbook_suggests_storage_permission_and_cache_recovery(tmp_path):
    plan_path = tmp_path / "plan.json"
    failing = tmp_path / "failing-build.py"
    failing.write_text(
        "import sys\n"
        "print('Permission denied: /tmp/skill-channel/linux-64', file=sys.stderr)\n"
        "print('No space left on device while writing package', file=sys.stderr)\n"
        "print('rattler cache lock is stale or corrupt', file=sys.stderr)\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(
            {
                "runbook": [
                    {
                        "id": "build",
                        "recommended": True,
                        "requires_confirmation": False,
                        "command": [sys.executable, str(failing)],
                        "stdout_path": str(tmp_path / "build.out"),
                        "stderr_path": str(tmp_path / "build.err"),
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
    assert "repair-output-directory-permissions" in action_ids
    assert "free-disk-space-or-change-output-dir" in action_ids
    assert "inspect-rattler-cache-or-lock" in action_ids


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
    assert '"code": "local-source-ref-mismatch"' in result.stdout


def test_rattler_local_source_ref_rejects_uninitialized_submodules(tmp_path):
    source = tmp_path / "klayout"
    channel = tmp_path / "channel"
    git_repo_with_uninitialized_submodule(source, "v0.30.9", tmp_path / "submodule-source")
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
    assert '"code": "local-source-submodule-missing"' in result.stdout
    assert '"missing_submodules": [' in result.stdout
    assert '"deps/model"' in result.stdout


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
