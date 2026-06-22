#!/usr/bin/env python
"""Run deterministic skill repository scenario checks.

The harness intentionally starts with provider modes that do not require live
agent credentials. It validates installability, scenario guardrails, command
boundaries, and fixture setup. Live provider adapters can be added without
changing the case format.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "tests" / "cases"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
DEFAULT_REPORTS_DIR = REPO_ROOT / "reports" / "skill-harness"
DEFAULT_SINGULARITY_BIN = "/opt/singularity-ce/4.1.1/bin/singularity"


class HarnessFailure(Exception):
    pass


def prepare_reports_dir(reports_dir: Path, keep_existing: bool = False) -> List[Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    if keep_existing:
        return []
    removed = []
    for path in sorted(reports_dir.glob("*.json")):
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def load_case(path: Path) -> Dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError:
            return json.loads(text)
        loaded = yaml.safe_load(text)
        if not isinstance(loaded, dict):
            raise HarnessFailure(f"{path}: case must load to an object")
        return loaded
    return json.loads(text)


def discover_cases() -> List[Tuple[str, Path]]:
    cases = []
    for path in sorted(CASES_DIR.glob("*")):
        if path.suffix not in {".json", ".yaml", ".yml"}:
            continue
        data = load_case(path)
        name = data.get("name") or path.stem
        cases.append((name, path))
    return cases


def skill_dir(skill: str) -> Path:
    path = REPO_ROOT / "plugins" / skill / "skills" / skill
    if not (path / "SKILL.md").exists():
        raise HarnessFailure(f"Unknown skill or missing SKILL.md: {skill}")
    return path


def read_skill_text(skill: str) -> str:
    return (skill_dir(skill) / "SKILL.md").read_text(encoding="utf-8")


def copy_workspace_fixture(name: str, destination: Path) -> None:
    source = FIXTURES_DIR / "workspaces" / name
    if not source.exists():
        raise HarnessFailure(f"Unknown workspace fixture: {name}")
    if destination.exists():
        shutil.rmtree(str(destination))
    shutil.copytree(str(source), str(destination))


def write_command_shim(bin_dir: Path, command: str, config: Dict, log_path: Path) -> None:
    exit_code = int(config.get("exit_code", 0))
    stdout = str(config.get("stdout", ""))
    stderr = str(config.get("stderr", ""))
    script = f"""#!/usr/bin/env python
import json
import pathlib
import sys

log_path = pathlib.Path({str(log_path)!r})
entry = {{"command": {command!r}, "argv": sys.argv[1:]}}
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(entry, sort_keys=True) + "\\n")
if {stdout!r}:
    print({stdout!r})
if {stderr!r}:
    print({stderr!r}, file=sys.stderr)
raise SystemExit({exit_code})
"""
    path = bin_dir / command
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)


def prepare_fake_bins(temp_root: Path, fake_bins: Dict) -> Tuple[Path, Path]:
    bin_dir = temp_root / "fake-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    log_path = temp_root / "command-log.jsonl"
    log_path.write_text("", encoding="utf-8")
    for command, config in fake_bins.items():
        if not isinstance(config, dict):
            config = {"stdout": str(config)}
        write_command_shim(bin_dir, command, config, log_path)
    return bin_dir, log_path


def command_log_text(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    lines = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            lines.append(line)
            continue
        argv = " ".join(str(part) for part in entry.get("argv", []))
        lines.append(f"{entry.get('command', '')} {argv}".strip())
    return "\n".join(lines)


def run_install(skill: str, install_targets: Iterable[str], temp_root: Path, env: Dict[str, str]) -> List[str]:
    outputs = []
    for target in install_targets:
        command = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "install.py"),
            "--target",
            target,
            "--skill",
            skill,
            "--mode",
            "copy",
            "--force",
        ]
        result = subprocess.run(
            command,
            cwd=str(REPO_ROOT),
            env=env,
            universal_newlines=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        outputs.append(result.stdout)
        if result.returncode != 0:
            raise HarnessFailure(f"install failed for target {target}: {result.stdout}")
    return outputs


def assert_contains(errors: List[str], haystack: str, needles: Iterable[str], label: str) -> None:
    for needle in needles:
        if needle not in haystack:
            errors.append(f"{label} missing expected text: {needle!r}")


def assert_not_contains(errors: List[str], haystack: str, needles: Iterable[str], label: str) -> None:
    for needle in needles:
        if needle in haystack:
            errors.append(f"{label} contains forbidden text: {needle!r}")


def run_static_provider(case: Dict, temp_root: Path, env: Dict[str, str], log_path: Path) -> Dict:
    skill = case["skill"]
    prompt = str(case.get("prompt", ""))
    install_targets = case.get("install_targets", ["codex"])
    if not isinstance(install_targets, list):
        raise HarnessFailure("install_targets must be a list")

    install_output = run_install(skill, install_targets, temp_root, env)
    skill_text = read_skill_text(skill)
    combined_text = "\n".join([prompt, skill_text, "\n".join(install_output)])

    assertions = case.get("assertions", {})
    errors: List[str] = []
    assert_contains(errors, skill_text, assertions.get("skill_must_contain", []), "skill")
    assert_not_contains(errors, skill_text, assertions.get("skill_must_not_contain", []), "skill")
    assert_contains(errors, prompt, assertions.get("prompt_must_contain", []), "prompt")
    assert_contains(errors, combined_text, assertions.get("must_contain", []), "combined")
    assert_not_contains(errors, combined_text, assertions.get("must_not_contain", []), "combined")

    for relpath in assertions.get("installed_files", ["SKILL.md"]):
        for target in install_targets:
            installed = installed_skill_dir(skill, target, env) / relpath
            if not installed.exists():
                errors.append(f"installed file missing for {target}: {relpath}")

    log_text = command_log_text(log_path)
    assert_contains(errors, log_text, assertions.get("required_commands", []), "command log")
    assert_not_contains(errors, log_text, assertions.get("forbidden_commands", []), "command log")

    return {
        "provider": "static",
        "install_output": install_output,
        "command_log": log_text,
        "errors": errors,
    }


def build_singularity_command(case: Dict, temp_root: Path, workspace: Path) -> List[str]:
    singularity_bin = str(case.get("singularity_bin") or DEFAULT_SINGULARITY_BIN)
    image = str(case.get("singularity_image") or "docker://ubuntu:24.04")
    container_command = case.get("singularity_command") or ["bash", "-lc", "true"]
    if isinstance(container_command, str):
        container_command = ["bash", "-lc", container_command]
    if not isinstance(container_command, list):
        raise HarnessFailure("singularity_command must be a string or list")

    home_dir = temp_root / "singularity-home"
    cache_dir = home_dir / ".cache"
    channel_dir = temp_root / "singularity-channel"
    for path in [home_dir, cache_dir, channel_dir]:
        path.mkdir(parents=True, exist_ok=True)

    env_prefix = [
        "env",
        "HOME=/tmp/skill-home",
        "PIXI_HOME=/tmp/skill-home/.pixi",
        "XDG_CACHE_HOME=/tmp/skill-home/.cache",
        "RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler",
        "CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel",
    ]

    return [
        singularity_bin,
        "exec",
        "--cleanenv",
        "--containall",
        "--home",
        f"{home_dir}:/tmp/skill-home",
        "--bind",
        f"{REPO_ROOT}:/mnt/skills",
        "--bind",
        f"{workspace}:/mnt/project",
        "--bind",
        f"{channel_dir}:/tmp/skill-channel",
        image,
        *env_prefix,
        *[str(part) for part in container_command],
    ]


def run_singularity_provider(case: Dict, provider: str, temp_root: Path, env: Dict[str, str], log_path: Path, workspace: Path) -> Dict:
    install_targets = case.get("install_targets", ["codex"])
    if not isinstance(install_targets, list):
        raise HarnessFailure("install_targets must be a list")

    skill = case["skill"]
    prompt = str(case.get("prompt", ""))
    install_output = run_install(skill, install_targets, temp_root, env)
    skill_text = read_skill_text(skill)
    command = build_singularity_command(case, temp_root, workspace)
    command_preview = shlex.join(command)
    combined_text = "\n".join([prompt, skill_text, "\n".join(install_output), command_preview])

    assertions = case.get("assertions", {})
    errors: List[str] = []
    assert_contains(errors, skill_text, assertions.get("skill_must_contain", []), "skill")
    assert_not_contains(errors, skill_text, assertions.get("skill_must_not_contain", []), "skill")
    assert_contains(errors, prompt, assertions.get("prompt_must_contain", []), "prompt")
    assert_contains(errors, combined_text, assertions.get("must_contain", []), "combined")
    assert_not_contains(errors, combined_text, assertions.get("must_not_contain", []), "combined")

    output = ""
    returncode = 0
    if provider == "singularity":
        singularity_bin = Path(command[0])
        if not singularity_bin.exists():
            errors.append(f"Singularity executable not found: {singularity_bin}")
        if not case.get("singularity_image"):
            errors.append("singularity provider requires singularity_image")
        if not case.get("singularity_command"):
            errors.append("singularity provider requires singularity_command")
        if not errors:
            result = subprocess.run(
                command,
                cwd=str(workspace),
                env=env,
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            output = result.stdout
            returncode = result.returncode
            if result.returncode != 0:
                errors.append(f"singularity command failed with exit {result.returncode}: {result.stdout}")

    log_text = command_log_text(log_path)
    assert_contains(errors, log_text, assertions.get("required_commands", []), "command log")
    assert_not_contains(errors, log_text, assertions.get("forbidden_commands", []), "command log")

    return {
        "provider": provider,
        "install_output": install_output,
        "command_preview": command_preview,
        "command_output": output,
        "command_returncode": returncode,
        "command_log": log_text,
        "errors": errors,
    }


def installed_skill_dir(skill: str, target: str, env: Dict[str, str]) -> Path:
    if target == "codex":
        return Path(env["CODEX_HOME"]) / "skills" / skill
    if target == "agents":
        return Path(env["AGENTS_HOME"]) / "skills" / skill
    if target == "claude":
        return Path(env["HOME"]) / ".claude" / "skills" / skill
    raise HarnessFailure(f"Unsupported install target in harness: {target}")


def run_live_provider(case: Dict, provider: str) -> Dict:
    return {
        "provider": provider,
        "errors": [
            f"{provider} is intentionally gated. Use deterministic providers in CI; "
            "add a separate opt-in live-agent workflow when credentials and sandboxing are configured."
        ],
    }


def run_case(path: Path, provider_override: str, reports_dir: Path, keep_temp: bool) -> bool:
    case = load_case(path)
    name = case.get("name") or path.stem
    provider = provider_override or case.get("provider", "static")
    start = time.time()

    temp_context = tempfile.TemporaryDirectory(prefix=f"skill-harness-{name}-")
    temp_root = Path(temp_context.name)
    try:
        workspace = temp_root / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        if case.get("workspace_fixture"):
            copy_workspace_fixture(str(case["workspace_fixture"]), workspace)

        fake_bin, log_path = prepare_fake_bins(temp_root, case.get("fake_bins", {}))
        home = temp_root / "home"
        home.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({str(k): str(v) for k, v in case.get("env", {}).items()})
        env.update(
            {
                "HOME": str(home),
                "CODEX_HOME": str(temp_root / "codex-home"),
                "AGENTS_HOME": str(temp_root / "agents-home"),
                "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                "SKILL_HARNESS_COMMAND_LOG": str(log_path),
            }
        )

        if provider in {"static", "prompt-only"}:
            result = run_static_provider(case, temp_root, env, log_path)
            result["provider"] = provider
        elif provider in {"singularity-dry-run", "singularity"}:
            result = run_singularity_provider(case, provider, temp_root, env, log_path, workspace)
        else:
            result = run_live_provider(case, provider)

        errors = result.get("errors", [])
        report = {
            "name": name,
            "case_file": str(path.relative_to(REPO_ROOT)),
            "skill": case.get("skill"),
            "provider": provider,
            "prompt": case.get("prompt", ""),
            "assertions": case.get("assertions", {}),
            "ok": not errors,
            "errors": errors,
            "duration_seconds": round(time.time() - start, 3),
            "workspace": str(workspace),
            "temp_root": str(temp_root) if keep_temp else "",
            "details": result,
        }
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / f"{name}.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

        status = "PASS" if report["ok"] else "FAIL"
        print(f"{status} {name}")
        for error in errors:
            print(f"  - {error}")
        return bool(report["ok"])
    finally:
        if keep_temp:
            print(f"Kept temp root for {name}: {temp_root}")
        else:
            temp_context.cleanup()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list", help="List discovered scenario cases.")

    run_parser = subparsers.add_parser("run", help="Run scenario cases.")
    run_parser.add_argument("cases", nargs="*", help="Case names or case file paths. Defaults to all cases.")
    run_parser.add_argument("--provider", default="", help="Override provider for every case.")
    run_parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    run_parser.add_argument(
        "--keep-existing-reports",
        action="store_true",
        help="Do not remove existing JSON reports before running selected cases.",
    )
    run_parser.add_argument("--keep-temp", action="store_true", help="Keep temporary roots for debugging.")
    return parser.parse_args()


def resolve_selected_cases(selected: List[str]) -> List[Path]:
    discovered = dict(discover_cases())
    if not selected:
        return [path for _, path in discover_cases()]

    paths = []
    for item in selected:
        candidate = Path(item)
        if candidate.exists():
            paths.append(candidate)
            continue
        if item in discovered:
            paths.append(discovered[item])
            continue
        raise HarnessFailure(f"Unknown case: {item}")
    return paths


def main() -> int:
    args = parse_args()
    if not args.command:
        print("ERROR: pass a command: list or run", file=sys.stderr)
        return 2
    if args.command == "list":
        for name, path in discover_cases():
            print(f"{name}\t{path.relative_to(REPO_ROOT)}")
        return 0

    try:
        case_paths = resolve_selected_cases(args.cases)
        prepare_reports_dir(args.reports_dir, keep_existing=args.keep_existing_reports)
        ok = True
        for path in case_paths:
            ok = run_case(path, args.provider, args.reports_dir, args.keep_temp) and ok
        return 0 if ok else 1
    except HarnessFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
