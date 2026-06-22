from monata_env_helpers import *


def test_record_manifest_appends_command_and_verification_payload(tmp_path):
    manifest = tmp_path / "session" / "monata-env-install-manifest.json"
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


def test_audit_manifest_blocks_corrupt_package_artifact_evidence(tmp_path):
    manifest = tmp_path / "session" / "monata-env-install-manifest.json"
    tools = ["ngspice", "openvaf-r", "klayout", "xschem"]
    artifact_dir = tmp_path / "channel" / "linux-64"
    artifact_dir.mkdir(parents=True)
    artifacts = []
    for tool in tools:
        artifact = artifact_dir / f"{tool}-1.0-0.conda"
        artifact.write_text("" if tool == "xschem" else "artifact\n", encoding="utf-8")
        artifacts.append(
            {
                "package": tool,
                "path": str(artifact),
                "filename": artifact.name,
                "size": artifact.stat().st_size,
            }
        )
    write_auditable_manifest(manifest, artifacts=artifacts)

    result = run([sys.executable, AUDIT_SCRIPT, "--manifest", manifest, "--require-artifacts", "--format", "json"])

    assert result.returncode == 1
    data = json.loads(result.stdout)
    requirements = {item["id"]: item for item in data["requirements"]}
    artifact_requirement = requirements["package-artifacts-recorded"]
    invalid = [{"package": "xschem", "path": str(artifact_dir / "xschem-1.0-0.conda"), "reason": "empty-file"}]
    assert artifact_requirement["ok"] is False
    assert artifact_requirement["invalid"] == invalid
    assert data["evidence"]["artifacts"]["invalid_files"] == invalid
    assert data["next_actions"][0]["evidence"]["invalid_artifacts"] == invalid


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
