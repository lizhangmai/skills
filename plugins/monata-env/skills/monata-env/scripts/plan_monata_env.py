#!/usr/bin/env python
"""Plan an AI-native monata-env setup session."""

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from detect_monata_tools import detect


SCRIPT_DIR = Path(__file__).resolve().parent
EXPECTED_SOURCE_REFS = {
    "klayout": "v0.30.9",
    "xschem": "3.4.7",
}
PIXI_PACKAGE_SPECS = {
    "ngspice": "ngspice=46.0",
    "openvaf-r": "openvaf-r",
    "klayout": "klayout=0.30.9",
    "xschem": "xschem=3.4.7",
}
EXPOSED_COMMANDS = {
    "ngspice": "ngspice",
    "openvaf-r": "openvaf-r",
    "klayout": "klayout",
    "xschem": "xschem",
}
CACHED_SKILLS_ROOT = Path.home() / ".cache" / "monata-env" / "skills"
DEFAULT_CONTAINER_IMAGE = "docker://python:3.12-slim"
DEFAULT_CONTAINER_STATE_DIR = Path("/tmp/monata-env-skill-test")
TEST_IMAGE_REQUIRED_COMMANDS = ["/usr/local/bin/python3", "git", "pixi"]


def command_string(command):
    return shlex.join(str(part) for part in command)


def resolve_container_image(value=None):
    if not value:
        return DEFAULT_CONTAINER_IMAGE
    text = str(value)
    if "://" in text:
        return text
    return str(Path(text).expanduser().resolve())


def default_test_image_output(session_dir, container_state_dir):
    if session_dir:
        return Path(session_dir) / "monata-env-test.sif"
    return Path(container_state_dir) / "monata-env-test.sif"


def find_skills_repo_root(helper_script):
    if not helper_script or not helper_script.exists():
        return None
    for candidate in helper_script.resolve().parents:
        if (
            candidate.joinpath("plugins", "monata-env", "skills", "monata-env", "scripts", "plan_monata_env.py").exists()
            and candidate.joinpath(
                "plugins",
                "conda-build",
                "skills",
                "conda-build",
                "scripts",
                "rattler_channel.py",
            ).exists()
        ):
            return candidate
    return None


def conda_build_helper_candidates():
    candidates = []
    try:
        plugins_dir = SCRIPT_DIR.parents[3]
        candidates.append(plugins_dir / "conda-build" / "skills" / "conda-build" / "scripts" / "rattler_channel.py")
    except IndexError:
        pass
    candidates.append(
        CACHED_SKILLS_ROOT
        / "plugins"
        / "conda-build"
        / "skills"
        / "conda-build"
        / "scripts"
        / "rattler_channel.py"
    )
    return candidates


def resolve_conda_build_helper(value=None):
    if value:
        return Path(value).expanduser().resolve()
    candidates = conda_build_helper_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def run_git(path, *args):
    result = subprocess.run(
        ["git", "-C", str(path), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def parse_key_path(values):
    parsed = {}
    for value in values or []:
        if "=" not in value:
            raise SystemExit(f"Expected package=path syntax: {value}")
        package, source = value.split("=", 1)
        package = package.strip()
        if not package:
            raise SystemExit(f"Package name cannot be empty: {value}")
        parsed[package] = Path(source).expanduser().resolve()
    return parsed


def local_source_status(package, path):
    target_ref = EXPECTED_SOURCE_REFS.get(package)
    item = {
        "path": str(path),
        "exists": path.exists(),
        "target_ref": target_ref,
        "status": "unchecked",
    }
    if not path.exists():
        item["status"] = "missing"
        return item
    if shutil.which("git") is None:
        item["status"] = "git-unavailable"
        return item
    inside = run_git(path, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        item["status"] = "not-git"
        return item
    head = run_git(path, "rev-parse", "HEAD")
    item["head"] = head
    if not target_ref:
        item["status"] = "ok"
        return item
    target = run_git(path, "rev-parse", "--verify", f"{target_ref}^{{commit}}")
    item["target_commit"] = target
    if not target:
        item["status"] = "target-ref-missing"
        return item
    if head == target:
        item["status"] = "ok"
    else:
        item["status"] = "ref-mismatch"
        item["recommended_worktree"] = f"/tmp/monata-sources/{package}-{target_ref}"
        item["worktree_command"] = [
            "git",
            "-C",
            str(path),
            "worktree",
            "add",
            "--detach",
            item["recommended_worktree"],
            target_ref,
        ]
    return item


def package_artifacts(output_dir, package):
    if output_dir is None or not output_dir.exists():
        return []
    patterns = [f"{package}-*.conda", f"{package}-*.tar.bz2"]
    artifacts = []
    for pattern in patterns:
        artifacts.extend(path for path in output_dir.rglob(pattern) if path.is_file())
    return sorted(str(path) for path in artifacts)


def channel_status(output_dir, packages):
    package_status = {}
    for package in packages:
        artifacts = package_artifacts(output_dir, package)
        package_status[package] = {
            "present": bool(artifacts),
            "artifacts": artifacts,
        }
    return {
        "output_dir": str(output_dir) if output_dir else "",
        "exists": bool(output_dir and output_dir.exists()),
        "packages": package_status,
        "missing": [package for package, item in package_status.items() if not item["present"]],
    }


def build_command(packages, output_dir, local_sources, helper_script):
    command = [
        sys.executable,
        str(helper_script),
        "build",
        "--recipe-set",
        "circuit-toolchain",
    ]
    for package in packages:
        command.extend(["--package", package])
    for package, path in local_sources.items():
        command.extend(["--local-source", f"{package}={path}"])
        if package in EXPECTED_SOURCE_REFS:
            command.extend(["--local-source-ref", f"{package}={EXPECTED_SOURCE_REFS[package]}"])
    command.append("--skip-existing")
    if output_dir:
        command.extend(["--output-dir", str(output_dir)])
    return command


def install_command(packages, output_dir, env_name):
    command = ["pixi", "global", "install", "--environment", env_name]
    if output_dir:
        command.extend(["--channel", output_dir.resolve().as_uri()])
    command.extend(["--channel", "conda-forge"])
    for package in packages:
        executable = EXPOSED_COMMANDS.get(package)
        if executable:
            command.extend(["--expose", f"{executable}={executable}"])
    for package in packages:
        command.append(PIXI_PACKAGE_SPECS.get(package, package))
    return command


def select_build_packages(packages, missing, local_sources):
    selected = set(missing)
    return [package for package in packages if package in selected]


def check_channel_command(packages, output_dir, helper_script):
    command = [
        sys.executable,
        str(helper_script),
        "check-channel",
        "--recipe-set",
        "circuit-toolchain",
    ]
    for package in packages:
        command.extend(["--package", package])
    if output_dir:
        command.extend(["--output-dir", str(output_dir)])
    return command


def upstream_installed_test_command(local_sources):
    command = [
        sys.executable,
        str(SCRIPT_DIR / "test_monata_env_upstream.py"),
        "--format",
        "json",
        "--profile",
        "basic",
    ]
    if "klayout" in local_sources:
        command.extend(["--klayout-source", str(local_sources["klayout"])])
    if "xschem" in local_sources:
        command.extend(["--xschem-source", str(local_sources["xschem"])])
    return command if len(command) > 6 else []


def record_after_command(
    manifest_path,
    kind,
    command,
    returncode_var,
    stdout_path=None,
    stderr_path=None,
    verification=None,
    artifact_dir=None,
    packages=None,
):
    record = [
        sys.executable,
        str(SCRIPT_DIR / "record_monata_env_session.py"),
        "--manifest",
        str(manifest_path),
        "--command-kind",
        kind,
        "--command",
        command_string(command),
        "--returncode",
        f"${returncode_var}",
    ]
    if stdout_path:
        record.extend(["--stdout-file", str(stdout_path)])
    if stderr_path:
        record.extend(["--stderr-file", str(stderr_path)])
    if verification:
        record.extend(["--verification", f"{verification}={stdout_path}"])
    if artifact_dir:
        record.extend(["--artifact-dir", str(artifact_dir)])
    for package in packages or []:
        record.extend(["--package", package])
    return {
        "returncode_var": returncode_var,
        "command": record,
    }


def runbook(commands, packages, build_packages, log_dir, artifact_dir, manifest_path, upstream_recommended):
    check_stdout = log_dir / "monata-env-check-channel.json"
    check_stderr = log_dir / "monata-env-check-channel.err"
    build_stdout = log_dir / "monata-env-build.out"
    build_stderr = log_dir / "monata-env-build.err"
    install_stdout = log_dir / "monata-env-install.out"
    install_stderr = log_dir / "monata-env-install.err"
    smoke_json = log_dir / "monata-env-smoke.json"
    smoke_stderr = log_dir / "monata-env-smoke.err"
    upstream_json = log_dir / "monata-env-upstream-installed.json"
    upstream_stderr = log_dir / "monata-env-upstream-installed.err"
    return [
        {
            "id": "check_channel",
            "description": "Inspect the requested local channel before building.",
            "recommended": True,
            "requires_confirmation": False,
            "timeout_seconds": 300,
            "command": commands["check_channel"],
            "stdout_path": str(check_stdout),
            "stderr_path": str(check_stderr),
            "record_after": record_after_command(
                manifest_path,
                "check_channel",
                commands["check_channel"],
                "CHECK_CHANNEL_RC",
                stdout_path=check_stdout,
                stderr_path=check_stderr,
                artifact_dir=artifact_dir,
                packages=packages,
            ),
        },
        {
            "id": "build",
            "description": "Build only missing or local-source packages, then record generated package artifacts.",
            "recommended": bool(commands["build"]),
            "requires_confirmation": True,
            "depends_on": ["check_channel"],
            "timeout_seconds": 7200,
            "command": commands["build"],
            "stdout_path": str(build_stdout),
            "stderr_path": str(build_stderr),
            "record_after": record_after_command(
                manifest_path,
                "build",
                commands["build"],
                "BUILD_RC",
                stdout_path=build_stdout,
                stderr_path=build_stderr,
                artifact_dir=artifact_dir,
                packages=build_packages,
            )
            if commands["build"]
            else None,
        },
        {
            "id": "install",
            "description": "Install exposed circuit-tool commands into the pixi global monata-env environment.",
            "recommended": True,
            "requires_confirmation": True,
            "depends_on": ["build"] if commands["build"] else ["check_channel"],
            "timeout_seconds": 1800,
            "command": commands["install"],
            "stdout_path": str(install_stdout),
            "stderr_path": str(install_stderr),
            "record_after": record_after_command(
                manifest_path,
                "install",
                commands["install"],
                "INSTALL_RC",
                stdout_path=install_stdout,
                stderr_path=install_stderr,
            ),
        },
        {
            "id": "smoke",
            "description": "Run direct installed-tool smoke tests without importing Monata or bootstrapping techlibs.",
            "recommended": True,
            "requires_confirmation": False,
            "depends_on": ["install"],
            "timeout_seconds": 600,
            "command": commands["smoke"],
            "stdout_path": str(smoke_json),
            "stderr_path": str(smoke_stderr),
            "record_after": record_after_command(
                manifest_path,
                "smoke",
                commands["smoke"],
                "SMOKE_RC",
                stdout_path=smoke_json,
                stderr_path=smoke_stderr,
                verification="smoke",
            ),
        },
        {
            "id": "upstream_installed_tests",
            "description": "Optionally run safe upstream test subsets against installed tools when local sources are available.",
            "recommended": upstream_recommended,
            "requires_confirmation": True,
            "depends_on": ["smoke"],
            "timeout_seconds": 1800,
            "command": commands["upstream_installed_tests"],
            "stdout_path": str(upstream_json),
            "stderr_path": str(upstream_stderr),
            "record_after": record_after_command(
                manifest_path,
                "upstream_installed_tests",
                commands["upstream_installed_tests"],
                "UPSTREAM_RC",
                stdout_path=upstream_json,
                stderr_path=upstream_stderr,
                verification="upstream_installed",
            )
            if commands["upstream_installed_tests"]
            else None,
        },
    ]


def container_runner_prefix(root, output_dir, container_image, helper_script, state_dir, extra_options=None):
    skills_repo_root = find_skills_repo_root(helper_script)
    repo_root_option = ""
    if skills_repo_root:
        repo_root_option = f"--repo-root {shlex.quote(str(skills_repo_root))} "
    options = "".join(extra_options or [])
    return (
        "python scripts/skill_container.py "
        f"--state-dir {shlex.quote(str(state_dir))} "
        f"{repo_root_option}"
        f"--workspace {shlex.quote(str(Path(root).resolve()))} "
        f"--channel {shlex.quote(str(output_dir))} "
        f"--image {shlex.quote(container_image)} "
        f"{options}"
    )


def container_planner_command(root, output_dir, container_image, helper_script, state_dir):
    skills_repo_root = find_skills_repo_root(helper_script)
    container_plan_script = "/mnt/skills/scripts/plan_monata_env.py"
    container_helper_arg = ""
    if skills_repo_root:
        container_plan_script = "/mnt/skills/plugins/monata-env/skills/monata-env/scripts/plan_monata_env.py"
        container_helper_arg = (
            " --conda-build-helper "
            "/mnt/skills/plugins/conda-build/skills/conda-build/scripts/rattler_channel.py"
        )
    return (
        container_runner_prefix(root, output_dir, container_image, helper_script, state_dir)
        + "--require-command python3 "
        "--dry-run -- "
        f"bash -lc 'cd /mnt/project && python3 {container_plan_script} "
        f"--root /mnt/project --output-dir /tmp/skill-channel "
        f"--session-dir /tmp/skill-home/monata-env-session{container_helper_arg} "
        "--write-manifest --format json'"
    )


def test_image_prepare_command(image_path, host_pixi_root=None, remote=False):
    command = [
        sys.executable,
        str(SCRIPT_DIR / "prepare_monata_env_test_image.py"),
        "--image",
        str(image_path),
        "--format",
        "json",
    ]
    if remote:
        command.append("--remote")
    if host_pixi_root:
        command.extend(["--pixi-binary", str(Path(host_pixi_root) / "bin" / "pixi")])
    return command_string(command)


def test_image_validate_command(root, output_dir, image_path, helper_script, state_dir):
    command = container_runner_prefix(root, output_dir, str(image_path), helper_script, state_dir)
    for required in TEST_IMAGE_REQUIRED_COMMANDS:
        command += f"--require-command {shlex.quote(required)} "
    return command + "-- true"


def test_image_plan(root, output_dir, image_path, helper_script, state_dir, host_pixi_root=None):
    return {
        "image": str(image_path),
        "required_commands": TEST_IMAGE_REQUIRED_COMMANDS,
        "prepare_command": test_image_prepare_command(image_path, host_pixi_root),
        "remote_prepare_command": test_image_prepare_command(image_path, remote=True),
        "validate_command": test_image_validate_command(root, output_dir, image_path, helper_script, state_dir),
    }


def container_install_smoke_command(
    root,
    output_dir,
    container_image,
    helper_script,
    host_pixi_root,
    state_dir,
    local_source_paths=None,
    include_upstream=False,
):
    if not host_pixi_root:
        return ""
    container_python = "/usr/local/bin/python3"
    plan_script = "/mnt/skills/scripts/plan_monata_env.py"
    execute_script = "/mnt/skills/scripts/execute_monata_env_runbook.py"
    container_helper_arg = ""
    skills_repo_root = find_skills_repo_root(helper_script)
    if skills_repo_root:
        plan_script = "/mnt/skills/plugins/monata-env/skills/monata-env/scripts/plan_monata_env.py"
        execute_script = (
            "/mnt/skills/plugins/monata-env/skills/monata-env/scripts/"
            "execute_monata_env_runbook.py"
        )
        container_helper_arg = (
            " --conda-build-helper "
            "/mnt/skills/plugins/conda-build/skills/conda-build/scripts/rattler_channel.py"
        )
    pixi_binary = Path(host_pixi_root) / "bin" / "pixi"
    bind = f"{pixi_binary}:/opt/host-pixi/bin/pixi:ro"
    source_options = []
    source_binds = []
    if include_upstream:
        for package, source_path in (local_source_paths or {}).items():
            container_source = f"/mnt/sources/{package}"
            source_binds.append(f"--bind {shlex.quote(f'{source_path}:{container_source}:ro')} ")
            source_options.append(f"--local-source {package}={container_source} ")
    runbook_steps = "--step install --step smoke"
    if include_upstream:
        runbook_steps += " --step upstream_installed_tests"
    return (
        container_runner_prefix(
            root,
            output_dir,
            container_image,
            helper_script,
            state_dir,
            extra_options=[
                f"--bind {shlex.quote(bind)} ",
                *source_binds,
                "--prepend-path /tmp/skill-home/.pixi/bin ",
                "--prepend-path /opt/host-pixi/bin ",
            ],
        )
        + f"--require-command {container_python} "
        "--require-command pixi "
        "-- "
        "bash -c 'cd /mnt/project && "
        "mkdir -p /tmp/skill-home/monata-env-session && "
        f"{container_python} {plan_script} "
        "--root /mnt/project --output-dir /tmp/skill-channel "
        f"--session-dir /tmp/skill-home/monata-env-session{container_helper_arg} "
        f"{''.join(source_options)}"
        "--write-manifest --format json "
        "> /tmp/skill-home/monata-env-session/plan.json && "
        f"{container_python} {execute_script} "
        "--manifest /tmp/skill-home/monata-env-session/monata-env-install-manifest.json "
        f"{runbook_steps} --allow-confirmation-required --format json'"
    )


def decisions(
    root,
    output_dir,
    local_source_paths,
    profiles,
    build_needed,
    container_image,
    helper_script,
    container_state_dir,
    test_image,
    host_pixi_root=None,
):
    source_paths = {package: str(path) for package, path in local_source_paths.items()}
    has_local_sources = bool(source_paths)
    upstream_recommended = profiles["upstream_installed"]["recommended"]
    if not build_needed:
        source_default = "existing_channel_only"
    elif has_local_sources:
        source_default = "local_sources"
    else:
        source_default = "network"
    isolation_command = container_planner_command(root, output_dir, container_image, helper_script, container_state_dir)
    isolated_commands = {"planner": isolation_command}
    live_install_command = container_install_smoke_command(
        root,
        output_dir,
        container_image,
        helper_script,
        host_pixi_root,
        container_state_dir,
    )
    if live_install_command:
        isolated_commands["install_smoke"] = live_install_command
    live_upstream_command = container_install_smoke_command(
        root,
        output_dir,
        container_image,
        helper_script,
        host_pixi_root,
        container_state_dir,
        local_source_paths=local_source_paths,
        include_upstream=bool(local_source_paths),
    )
    if live_upstream_command:
        isolated_commands["install_smoke_upstream"] = live_upstream_command
    return [
        {
            "id": "global_environment",
            "prompt": "Create or update the pixi global monata-env environment and exposed command shims?",
            "default": "approve",
            "options": [
                {
                    "id": "approve",
                    "label": "Update monata-env",
                    "recommended": True,
                    "effect": "Runs pixi global install only for the monata-env environment.",
                },
                {
                    "id": "plan_only",
                    "label": "Plan only",
                    "recommended": False,
                    "effect": "Writes the manifest seed and stops before mutating pixi global state.",
                },
            ],
        },
        {
            "id": "source_policy",
            "prompt": "How should missing circuit-tool packages be sourced?",
            "default": source_default,
            "options": [
                {
                    "id": "local_sources",
                    "label": "Use provided local sources",
                    "recommended": build_needed and has_local_sources,
                    "sources": source_paths,
                    "effect": "Builds from trusted local checkouts and still validates required upstream refs.",
                },
                {
                    "id": "network",
                    "label": "Fetch pinned upstream sources",
                    "recommended": build_needed and not has_local_sources,
                    "effect": "Uses the bundled recipes' pinned public upstream URLs.",
                },
                {
                    "id": "existing_channel_only",
                    "label": "Use existing channel only",
                    "recommended": not build_needed,
                    "effect": "Skips package builds and installs only artifacts already present in the local channel.",
                },
            ],
        },
        {
            "id": "test_isolation",
            "prompt": "Where should live skill validation run?",
            "default": "singularity",
            "options": [
                {
                    "id": "singularity",
                    "label": "Isolated Singularity state",
                    "recommended": True,
                    "command": isolation_command,
                    "commands": isolated_commands,
                    "effect": "Uses temporary HOME, PIXI_HOME, caches, and channel directories.",
                },
                {
                    "id": "host",
                    "label": "Current host environment",
                    "recommended": False,
                    "effect": "Fastest path but can touch the user's current pixi and cache state.",
                },
            ],
        },
        {
            "id": "test_image",
            "prompt": "Which container image should live install and upstream tests use?",
            "default": "prepare_dedicated",
            "options": [
                {
                    "id": "prepare_dedicated",
                    "label": "Prepare dedicated image",
                    "recommended": True,
                    "command": test_image["prepare_command"],
                    "remote_command": test_image["remote_prepare_command"],
                    "validation_command": test_image["validate_command"],
                    "required_commands": test_image["required_commands"],
                    "effect": "Builds or updates a local SIF with python3, git, and pixi so live tests do not depend on host tool shims.",
                },
                {
                    "id": "host_pixi_bind",
                    "label": "Bind host pixi only",
                    "recommended": bool(host_pixi_root),
                    "effect": "Uses the current container image and binds only the host pixi executable read-only; useful when image build is unavailable.",
                },
                {
                    "id": "provided_image",
                    "label": "Use provided image",
                    "recommended": False,
                    "validation_command": test_image["validate_command"],
                    "required_commands": test_image["required_commands"],
                    "effect": "Use after the user provides a local .sif or reachable image that already contains required commands.",
                },
            ],
        },
        {
            "id": "upstream_test_profile",
            "prompt": "How much upstream project test coverage should run after installing tools?",
            "default": "basic" if upstream_recommended else "skip",
            "options": [
                {
                    "id": "skip",
                    "label": "Skip upstream tests",
                    "recommended": not upstream_recommended,
                    "effect": "Runs only the installed-tool smoke test.",
                },
                {
                    "id": "basic",
                    "label": "Basic upstream-installed tests",
                    "recommended": upstream_recommended,
                    "effect": "Runs safe upstream subsets against installed KLayout and Xschem when source checkouts exist.",
                },
                {
                    "id": "full",
                    "label": "Full upstream regressions",
                    "recommended": False,
                    "effect": "Runs broader upstream suites only after explicit user approval.",
                },
            ],
        },
    ]


def test_profiles(local_sources):
    upstream_recommended = any(package in local_sources for package in ("klayout", "xschem"))
    return {
        "installed_smoke": {
            "recommended": True,
            "requires_local_source": False,
            "description": "Fast installed-tool smoke test that does not import Monata or use techlibs.",
        },
        "upstream_installed": {
            "recommended": upstream_recommended,
            "requires_local_source": True,
            "description": "Run safe upstream test subsets against installed tools when trusted local source checkouts are available.",
        },
        "upstream_full": {
            "recommended": False,
            "requires_local_source": True,
            "description": "Run broader upstream regression suites only when the user accepts longer runtime and extra dependencies.",
        },
    }


def questions(local_sources):
    items = []
    if any(item["status"] == "ref-mismatch" for item in local_sources.values()):
        items.append(
            {
                "id": "local_source_worktree",
                "question": "Local source checkout is not at the recipe ref. Create a temporary detached worktree instead of changing the user's checkout?",
                "recommended": True,
            }
        )
    if any(
        item["status"] in {"missing", "not-git", "target-ref-missing", "git-unavailable"}
        for item in local_sources.values()
    ):
        items.append(
            {
                "id": "local_source_repair",
                "question": "One or more local sources cannot be validated, or git is unavailable. Ask the user for a corrected path, tag, archive, or validation-capable container before building?",
                "recommended": True,
            }
        )
    return items


def create_plan(
    root,
    output_dir,
    local_source_values,
    env_name,
    conda_build_helper=None,
    container_image=None,
    session_dir=None,
    container_state_dir=None,
    test_image_output=None,
    host_pixi_root=None,
):
    detected = detect(root)
    packages = detected["packages"]
    helper_script = resolve_conda_build_helper(conda_build_helper)
    resolved_container_image = resolve_container_image(container_image)
    resolved_session_dir = Path(session_dir).expanduser().resolve() if session_dir else output_dir
    if container_state_dir:
        resolved_container_state_dir = Path(container_state_dir).expanduser().resolve()
    elif session_dir:
        resolved_container_state_dir = resolved_session_dir / "container-state"
    else:
        resolved_container_state_dir = DEFAULT_CONTAINER_STATE_DIR
    resolved_test_image_output = (
        Path(test_image_output).expanduser().resolve()
        if test_image_output
        else default_test_image_output(resolved_session_dir if session_dir else None, resolved_container_state_dir).resolve()
    )
    resolved_host_pixi_root = Path(host_pixi_root).expanduser().resolve() if host_pixi_root else None
    local_source_paths = parse_key_path(local_source_values)
    local_sources = {
        package: local_source_status(package, path)
        for package, path in local_source_paths.items()
    }
    channel = channel_status(output_dir, packages)
    missing = channel["missing"]
    build_packages = select_build_packages(packages, missing, local_source_paths)
    selected_local_sources = {
        package: path
        for package, path in local_source_paths.items()
        if package in build_packages
    }
    tools = {
        package: {
            "command": EXPOSED_COMMANDS.get(package, package),
            "path": shutil.which(EXPOSED_COMMANDS.get(package, package)),
        }
        for package in packages
    }
    manifest_path = (
        resolved_session_dir / "monata-env-install-manifest.json"
        if resolved_session_dir
        else Path("monata-env-install-manifest.json")
    )
    commands = {
        "check_channel": check_channel_command(packages, output_dir, helper_script),
        "build": build_command(build_packages, output_dir, selected_local_sources, helper_script) if build_packages else [],
        "install": install_command(packages, output_dir, env_name),
        "smoke": [sys.executable, str(SCRIPT_DIR / "smoke_monata_env_tools.py"), "--format", "json"],
        "upstream_installed_tests": upstream_installed_test_command(local_source_paths),
    }
    profiles = test_profiles(local_source_paths)
    test_image = test_image_plan(
        root,
        output_dir,
        resolved_test_image_output,
        helper_script,
        resolved_container_state_dir,
        resolved_host_pixi_root,
    )
    return {
        "mode": "ai-native-session",
        "root": str(Path(root).resolve()),
        "env_name": env_name,
        "packages": packages,
        "detector": detected,
        "channel": channel,
        "session": {
            "dir": str(resolved_session_dir) if resolved_session_dir else "",
            "purpose": "Stores the monata-env setup manifest and runbook logs.",
        },
        "container": {
            "image": resolved_container_image,
            "state_dir": str(resolved_container_state_dir),
            "host_pixi_root": str(resolved_host_pixi_root) if resolved_host_pixi_root else "",
            "test_image": test_image,
            "live_install_smoke_command": container_install_smoke_command(
                root,
                output_dir,
                resolved_container_image,
                helper_script,
                resolved_host_pixi_root,
                resolved_container_state_dir,
            ),
            "live_install_smoke_upstream_command": container_install_smoke_command(
                root,
                output_dir,
                resolved_container_image,
                helper_script,
                resolved_host_pixi_root,
                resolved_container_state_dir,
                local_source_paths=local_source_paths,
                include_upstream=bool(local_source_paths),
            ),
        },
        "local_sources": local_sources,
        "tools": tools,
        "helper": {
            "conda_build_script": str(helper_script),
            "conda_build_script_exists": helper_script.exists(),
        },
        "questions": questions(local_sources),
        "decisions": decisions(
            root,
            output_dir,
            local_source_paths,
            profiles,
            bool(build_packages),
            resolved_container_image,
            helper_script,
            resolved_container_state_dir,
            test_image,
            resolved_host_pixi_root,
        ),
        "commands": commands,
        "runbook": runbook(
            commands,
            packages,
            build_packages,
            resolved_session_dir,
            output_dir,
            manifest_path,
            profiles["upstream_installed"]["recommended"],
        ),
        "test_profiles": profiles,
        "build_needed": bool(build_packages),
        "build_packages": build_packages,
        "manifest": {
            "path": str(manifest_path),
            "purpose": "Record choices, package artifacts, source refs, install command, and verification results.",
        },
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Monata workspace to inspect.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Final local conda channel directory.")
    parser.add_argument("--local-source", action="append", default=[], help="Trusted local checkout as package=path.")
    parser.add_argument("--env-name", default="monata-env", help="pixi global environment name.")
    parser.add_argument("--conda-build-helper", type=Path, help="Path to conda-build helper rattler_channel.py.")
    parser.add_argument("--container-image", help="Singularity image URI or local .sif path for isolated live checks.")
    parser.add_argument("--session-dir", type=Path, help="Directory for the manifest and runbook logs.")
    parser.add_argument(
        "--host-pixi-root",
        type=Path,
        help="Host pixi installation root to bind read-only for isolated live install/smoke checks.",
    )
    parser.add_argument(
        "--container-state-dir",
        type=Path,
        help="Host directory for isolated Singularity HOME, pixi, rattler, and image cache state.",
    )
    parser.add_argument(
        "--test-image-output",
        type=Path,
        help="Output .sif path for a dedicated monata-env live-test image.",
    )
    parser.add_argument("--format", choices=("json", "summary"), default="json")
    parser.add_argument("--write-manifest", action="store_true", help="Write a manifest seed next to the output channel.")
    return parser.parse_args()


def print_summary(plan):
    print(f"mode: {plan['mode']}")
    print("packages: " + " ".join(plan["packages"]))
    missing = plan["channel"]["missing"]
    print("missing: " + (" ".join(missing) if missing else "none"))
    for question in plan["questions"]:
        print(f"question[{question['id']}]: {question['question']}")


def write_manifest_seed(plan):
    path = Path(plan["manifest"]["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "plan": plan,
        "execution": {
            "commands_run": [],
            "artifacts": [],
        },
        "verification": {
            "smoke": None,
            "upstream_installed": None,
        },
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    plan = create_plan(
        args.root,
        args.output_dir.resolve(),
        args.local_source,
        args.env_name,
        args.conda_build_helper,
        args.container_image,
        args.session_dir,
        args.container_state_dir,
        args.test_image_output,
        args.host_pixi_root,
    )
    if args.write_manifest:
        write_manifest_seed(plan)
    if args.format == "summary":
        print_summary(plan)
    else:
        print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
