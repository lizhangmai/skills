from monata_env_helpers import *


def test_upstream_tester_reports_structured_missing_source_errors(tmp_path):
    work_dir = tmp_path / "work"
    missing_klayout = tmp_path / "missing-klayout"
    missing_xschem = tmp_path / "missing-xschem"

    result = run(
        [
            sys.executable,
            UPSTREAM_SCRIPT,
            "--klayout-source",
            missing_klayout,
            "--xschem-source",
            missing_xschem,
            "--work-dir",
            work_dir,
            "--format",
            "json",
        ]
    )

    assert result.returncode == 1, result.stdout
    data = json.loads(result.stdout)
    assert data["profiles"]["klayout"]["error"]["code"] == "source-missing"
    assert data["profiles"]["xschem"]["error"]["code"] == "source-missing"


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


def test_container_upstream_command_quotes_paths_with_spaces(tmp_path):
    workspace = tmp_path / "workspace with spaces"
    output_dir = tmp_path / "channel with spaces"
    session_dir = tmp_path / "session with spaces"
    image = tmp_path / "monata env python.sif"
    host_pixi_root = tmp_path / "host pixi"
    klayout_source = tmp_path / "klayout source"
    xschem_source = tmp_path / "xschem source"
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
    command = data["container"]["live_install_smoke_upstream_command"]
    argv = shlex.split(command)
    assert argv[argv.index("--state-dir") + 1] == str(session_dir.resolve() / "container-state")
    assert argv[argv.index("--workspace") + 1] == str(workspace.resolve())
    assert argv[argv.index("--channel") + 1] == str(output_dir.resolve())
    assert argv[argv.index("--image") + 1] == str(image.resolve())
    binds = [argv[index + 1] for index, token in enumerate(argv) if token == "--bind"]
    assert f"{host_pixi_root.resolve() / 'bin' / 'pixi'}:/opt/host-pixi/bin/pixi:ro" in binds
    assert f"{klayout_source.resolve()}:/mnt/sources/klayout:ro" in binds
    assert f"{xschem_source.resolve()}:/mnt/sources/xschem:ro" in binds
    payload = argv[argv.index("--") + 1 :]
    assert payload[:2] == ["bash", "-c"]
    assert "--local-source klayout=/mnt/sources/klayout" in payload[2]
    assert "--local-source xschem=/mnt/sources/xschem" in payload[2]
    assert "--upstream-profile basic" in payload[2]


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


def test_upstream_script_runs_klayout_testdata_and_stream_wrapper(tmp_path):
    source = tmp_path / "klayout"
    test_dir = source / "testdata" / "klayout_main"
    env_prefix = tmp_path / "monata-env"
    work_dir = tmp_path / "work"
    test_dir.mkdir(parents=True)
    (env_prefix / "bin").mkdir(parents=True)
    (test_dir / "test12.py").write_text("print('upstream klayout test')\n", encoding="utf-8")
    klayout = env_prefix / "bin" / "klayout"
    write_executable(
        klayout,
        f"#!{sys.executable}\n"
        "import re, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "script = Path(args[args.index('-r') + 1])\n"
        "text = script.read_text()\n"
        "match = re.search(r\"layout\\.write\\(['\\\"]([^'\\\"]+)\", text)\n"
        "if match:\n"
        "    Path(match.group(1)).write_bytes(b'gds')\n"
        "    print('wrote ' + match.group(1))\n"
        "else:\n"
        "    print('ran upstream testdata')\n",
    )
    strm2txt = env_prefix / "bin" / "strm2txt"
    write_executable(
        strm2txt,
        f"#!{sys.executable}\n"
        "import sys\n"
        "from pathlib import Path\n"
        "Path(sys.argv[2]).write_text('begin_lib\\nend_lib\\n', encoding='utf-8')\n",
    )

    result = run(
        [
            sys.executable,
            UPSTREAM_SCRIPT,
            "--format",
            "json",
            "--klayout-source",
            source,
            "--env-prefix",
            env_prefix,
            "--work-dir",
            work_dir,
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    checks = data["profiles"]["klayout"]["checks"]
    assert [check["id"] for check in checks] == [
        "klayout-main-test12",
        "klayout-gds-generate-for-strm2txt",
        "klayout-strm2txt-wrapper",
    ]
    assert checks[0]["command"][0] == str(klayout.resolve())
    assert checks[2]["command"][0] == str(strm2txt.resolve())
    assert checks[2]["output_size"] > 0


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

