"""Container command construction for monata-env live validation."""

import shlex
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
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


def container_cache_strategy(state_dir):
    state = Path(state_dir)
    return {
        "state_dir": str(state),
        "home_dir": str(state / "home"),
        "pixi_home": str(state / "home" / ".pixi"),
        "rattler_cache_dir": str(state / "home" / ".cache" / "rattler"),
        "singularity_cache_dir": str(state / "singularity-cache"),
        "singularity_tmp_dir": str(state / "singularity-tmp"),
    }


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


def container_runner_argv(root, output_dir, container_image, helper_script, state_dir, extra_options=None):
    skills_repo_root = find_skills_repo_root(helper_script)
    command = [
        "python",
        "scripts/skill_container.py",
        "--state-dir",
        str(state_dir),
    ]
    if skills_repo_root:
        command.extend(["--repo-root", str(skills_repo_root)])
    command.extend(
        [
            "--workspace",
            str(Path(root).resolve()),
            "--channel",
            str(output_dir),
            "--image",
            container_image,
        ]
    )
    command.extend(extra_options or [])
    return command


def container_runner_prefix(root, output_dir, container_image, helper_script, state_dir, extra_options=None):
    return command_string(container_runner_argv(root, output_dir, container_image, helper_script, state_dir, extra_options))


def container_planner_command(root, output_dir, container_image, helper_script, state_dir, env_name):
    skills_repo_root = find_skills_repo_root(helper_script)
    container_plan_script = "/mnt/skills/scripts/plan_monata_env.py"
    plan_args = [
        "python3",
        container_plan_script,
        "--root",
        "/mnt/project",
        "--output-dir",
        "/tmp/skill-channel",
        "--session-dir",
        "/tmp/skill-home/monata-env-session",
        "--env-name",
        env_name,
    ]
    if skills_repo_root:
        container_plan_script = "/mnt/skills/plugins/monata-env/skills/monata-env/scripts/plan_monata_env.py"
        plan_args[1] = container_plan_script
        plan_args.extend(
            [
                "--conda-build-helper",
                "/mnt/skills/plugins/conda-build/skills/conda-build/scripts/rattler_channel.py",
            ]
        )
    plan_args.extend(["--write-manifest", "--format", "json"])
    inner = "cd /mnt/project && {}".format(command_string(plan_args))
    command = container_runner_argv(root, output_dir, container_image, helper_script, state_dir)
    command.extend(["--require-command", "python3", "--dry-run", "--", "bash", "-lc", inner])
    return command_string(command)


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
    command = container_runner_argv(root, output_dir, str(image_path), helper_script, state_dir)
    for required in TEST_IMAGE_REQUIRED_COMMANDS:
        command.extend(["--require-command", required])
    command.extend(["--", "true"])
    return command_string(command)


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
    env_name="monata-env",
    local_source_paths=None,
    include_build=False,
    include_upstream=False,
    upstream_profile="basic",
    timeout_seconds=None,
):
    if not host_pixi_root:
        return ""
    container_python = "/usr/local/bin/python3"
    plan_script = "/mnt/skills/scripts/plan_monata_env.py"
    execute_script = "/mnt/skills/scripts/execute_monata_env_runbook.py"
    plan_args = [
        container_python,
        plan_script,
        "--root",
        "/mnt/project",
        "--output-dir",
        "/tmp/skill-channel",
        "--session-dir",
        "/tmp/skill-home/monata-env-session",
        "--env-name",
        env_name,
    ]
    skills_repo_root = find_skills_repo_root(helper_script)
    if skills_repo_root:
        plan_script = "/mnt/skills/plugins/monata-env/skills/monata-env/scripts/plan_monata_env.py"
        execute_script = (
            "/mnt/skills/plugins/monata-env/skills/monata-env/scripts/"
            "execute_monata_env_runbook.py"
        )
        plan_args[1] = plan_script
        plan_args.extend(
            [
                "--conda-build-helper",
                "/mnt/skills/plugins/conda-build/skills/conda-build/scripts/rattler_channel.py",
            ]
        )
    pixi_binary = Path(host_pixi_root) / "bin" / "pixi"
    bind = f"{pixi_binary}:/opt/host-pixi/bin/pixi:ro"
    source_binds = []
    if include_upstream or include_build:
        for package, source_path in (local_source_paths or {}).items():
            container_source = f"/mnt/sources/{package}"
            source_binds.extend(["--bind", f"{source_path}:{container_source}:ro"])
            plan_args.extend(["--local-source", f"{package}={container_source}"])
    if include_upstream:
        plan_args.extend(["--upstream-profile", upstream_profile])
    plan_args.extend(["--write-manifest", "--format", "json"])
    runbook_steps = ["--step", "check_channel"]
    if include_build:
        runbook_steps.extend(["--step", "build"])
    runbook_steps.extend(["--step", "install", "--step", "smoke"])
    if include_upstream:
        runbook_steps.extend(["--step", "upstream_installed_tests"])
    runbook_steps.extend(["--step", "audit"])
    execute_args = [
        container_python,
        execute_script,
        "--manifest",
        "/tmp/skill-home/monata-env-session/monata-env-install-manifest.json",
        *runbook_steps,
        "--allow-confirmation-required",
        "--format",
        "json",
    ]
    inner = (
        "cd /mnt/project && "
        "mkdir -p /tmp/skill-home/monata-env-session && "
        "{} > /tmp/skill-home/monata-env-session/plan.json && {}".format(
            command_string(plan_args),
            command_string(execute_args),
        )
    )
    extra_options = [
        "--bind",
        bind,
        *source_binds,
        "--prepend-path",
        "/tmp/skill-home/.pixi/bin",
        "--prepend-path",
        "/opt/host-pixi/bin",
    ]
    if timeout_seconds:
        extra_options.extend(["--timeout-seconds", str(timeout_seconds)])
    command = container_runner_argv(
        root,
        output_dir,
        container_image,
        helper_script,
        state_dir,
        extra_options=extra_options,
    )
    command.extend(["--require-command", container_python, "--require-command", "pixi", "--", "bash", "-c", inner])
    return command_string(command)
