#!/usr/bin/env python
"""Run optional upstream test profiles against installed monata-env tools."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_ENV_NAME = "monata-env"


def run(command, cwd=None, env=None, timeout=300):
    command = [str(part) for part in command]
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
        returncode = result.returncode
        output = result.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        output = (output + f"\ntimed out after {timeout}s").strip() + "\n"
        returncode = 124
    return {
        "command": command,
        "cwd": str(cwd) if cwd else "",
        "returncode": returncode,
        "output": output[-6000:],
    }


def skipped(reason):
    return {
        "ok": True,
        "reason": reason,
        "checks": [],
    }


def failure(reason, source=None):
    item = {
        "ok": False,
        "reason": reason,
        "checks": [],
    }
    if source is not None:
        item["source"] = str(source)
    return item


def checks_reason(checks):
    if all(item["returncode"] == 0 for item in checks):
        return "ok"
    if any(item["returncode"] == 124 for item in checks):
        return "command-timeout"
    return "command-failed"


def env_executable(names, env_name=None, env_prefix=None):
    if isinstance(names, str):
        names = (names,)
    prefixes = []
    if env_prefix:
        prefixes.append(Path(env_prefix).expanduser().resolve())
    if env_name:
        prefix = pixi_env_prefix(env_name)
        if prefix:
            prefixes.append(prefix)
    for prefix in prefixes:
        for name in names:
            candidate = prefix / "bin" / name
            if candidate.exists():
                return str(candidate)
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def source_path(value):
    if value is None:
        return None
    return Path(value).expanduser().resolve()


def pixi_env_prefix(env_name):
    pixi_home = os.environ.get("PIXI_HOME")
    if pixi_home:
        candidate = Path(pixi_home).expanduser() / "envs" / env_name
        if candidate.exists():
            return candidate
    pixi = shutil.which("pixi")
    if pixi:
        candidate = Path(pixi).resolve().parent.parent / "envs" / env_name
        if candidate.exists():
            return candidate
    return None


def env_python(env_name, env_prefix):
    candidates = []
    if env_prefix:
        candidates.append(Path(env_prefix).expanduser().resolve() / "bin" / "python")
    prefix = pixi_env_prefix(env_name)
    if prefix:
        candidates.append(prefix / "bin" / "python")
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("python")


def run_klayout_upstream(source, work_dir, env_name, env_prefix, timeout):
    if source is None:
        return skipped("source-not-provided")
    if not source.exists():
        return failure("source-missing", source)

    klayout = env_executable("klayout", env_name=env_name, env_prefix=env_prefix)
    if not klayout:
        return failure("tool-missing", source)

    checks = []
    script = source / "testdata" / "klayout_main" / "test12.py"
    if not script.exists():
        return failure("source-test-missing", source)
    checks.append(run([klayout, "-b", "-r", script], cwd=work_dir, timeout=timeout))

    # If the pixi global environment Python can be located, also run a small
    # upstream Python-binding test that reads upstream GDS/GDS2 text fixtures.
    python = env_python(env_name, env_prefix)
    import_db = source / "testdata" / "pymod" / "import_db.py"
    if python and import_db.exists():
        checks.append(run([python, import_db], cwd=work_dir, timeout=timeout))

    ok = all(item["returncode"] == 0 for item in checks)
    return {
        "ok": ok,
        "reason": checks_reason(checks),
        "source": str(source),
        "checks": checks,
    }


def copy_xschem_test_tree(source, work_dir):
    root = work_dir / "xschem-upstream"
    tests_dest = root / "tests"
    library_dest = root / "xschem_library"
    shutil.copytree(source / "tests", tests_dest)
    shutil.copytree(source / "xschem_library", library_dest)
    return tests_dest


def run_xschem_basic_create_save(tests_dir, xschem, timeout):
    output = tests_dir / "create_save" / "results" / "simple_inv.sch"
    output.parent.mkdir(parents=True, exist_ok=True)
    check = run(
        [
            xschem,
            output,
            "--pipe",
            "-d",
            "1",
            "--script",
            "create_save/tests/simple_inv.tcl",
        ],
        cwd=tests_dir,
        timeout=timeout,
    )
    check["id"] = "xschem-basic-create-save"
    check["output_file"] = str(output)
    check["output_size"] = output.stat().st_size if output.exists() else 0
    return check


def run_xschem_upstream(source, work_dir, env_name, env_prefix, profile, timeout):
    if source is None:
        return skipped("source-not-provided")
    if not source.exists():
        return failure("source-missing", source)
    if not (source / "tests").is_dir() or not (source / "xschem_library").is_dir():
        return failure("source-test-missing", source)
    xschem = env_executable("xschem", env_name=env_name, env_prefix=env_prefix)
    if not xschem:
        return failure("tool-missing", source)
    tclsh = env_executable(("tclsh", "tclsh8.6", "tclsh8.7"), env_name=env_name, env_prefix=env_prefix)
    if profile == "full" and not tclsh:
        return failure("tclsh-missing", source)

    tests_dir = copy_xschem_test_tree(source, work_dir)
    checks = [run_xschem_basic_create_save(tests_dir, xschem, timeout)]
    if profile == "full":
        if checks[0]["returncode"] == 0:
            check = run([tclsh, "run_regression.tcl"], cwd=tests_dir, timeout=timeout)
            check["id"] = "xschem-full-regression"
            checks.append(check)
    return {
        "ok": all(check["returncode"] == 0 for check in checks),
        "reason": checks_reason(checks),
        "source": str(source),
        "checks": checks,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--klayout-source", type=Path, help="KLayout upstream checkout containing testdata/.")
    parser.add_argument("--xschem-source", type=Path, help="Xschem upstream checkout containing tests/ and xschem_library/.")
    parser.add_argument("--env-name", default=DEFAULT_ENV_NAME, help="pixi global environment name.")
    parser.add_argument("--env-prefix", type=Path, help="Installed environment prefix, used for env-internal tools.")
    parser.add_argument("--profile", choices=("basic", "full"), default="basic", help="Upstream test depth.")
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    parser.add_argument("--work-dir", type=Path, help="Working directory for copied upstream tests.")
    parser.add_argument("--keep-work-dir", action="store_true")
    parser.add_argument("--timeout", type=int, default=300, help="Per-command timeout in seconds.")
    return parser.parse_args()


def run_profiles(args):
    cleanup = None
    if args.work_dir:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="monata-env-upstream-tests-")
        work_dir = Path(cleanup.name)
    try:
        profiles = {
            "klayout": run_klayout_upstream(
                source_path(args.klayout_source),
                work_dir,
                args.env_name,
                args.env_prefix,
                args.timeout,
            ),
            "xschem": run_xschem_upstream(
                source_path(args.xschem_source),
                work_dir,
                args.env_name,
                args.env_prefix,
                args.profile,
                args.timeout,
            ),
        }
        return {
            "ok": all(item["ok"] for item in profiles.values()),
            "profile": args.profile,
            "work_dir": str(work_dir),
            "profiles": profiles,
        }
    finally:
        if cleanup is not None and not args.keep_work_dir:
            cleanup.cleanup()


def print_summary(report):
    for name, item in report["profiles"].items():
        status = "PASS" if item["ok"] else "FAIL"
        print(f"{status} {name}: {item['reason']}")


def main():
    args = parse_args()
    report = run_profiles(args)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
