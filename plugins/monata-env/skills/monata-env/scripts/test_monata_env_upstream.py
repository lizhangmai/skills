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
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )
    return {
        "command": [str(part) for part in command],
        "cwd": str(cwd) if cwd else "",
        "returncode": result.returncode,
        "output": result.stdout[-6000:],
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


def command_path(name):
    return shutil.which(name)


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

    klayout = command_path("klayout")
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
        "reason": "ok" if ok else "command-failed",
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


def run_xschem_upstream(source, work_dir, profile, timeout):
    if source is None:
        return skipped("source-not-provided")
    if not source.exists():
        return failure("source-missing", source)
    if not (source / "tests").is_dir() or not (source / "xschem_library").is_dir():
        return failure("source-test-missing", source)
    if not command_path("xschem"):
        return failure("tool-missing", source)
    if profile == "full" and not command_path("tclsh"):
        return failure("tclsh-missing", source)

    tests_dir = copy_xschem_test_tree(source, work_dir)
    if profile == "full":
        check = run(["tclsh", "run_regression.tcl"], cwd=tests_dir, timeout=timeout)
    else:
        output = tests_dir / "create_save" / "results" / "simple_inv.sch"
        output.parent.mkdir(parents=True, exist_ok=True)
        check = run(
            [
                "xschem",
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
        check["output_file"] = str(output)
        check["output_size"] = output.stat().st_size if output.exists() else 0
    return {
        "ok": check["returncode"] == 0,
        "reason": "ok" if check["returncode"] == 0 else "command-failed",
        "source": str(source),
        "checks": [check],
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--klayout-source", type=Path, help="KLayout upstream checkout containing testdata/.")
    parser.add_argument("--xschem-source", type=Path, help="Xschem upstream checkout containing tests/ and xschem_library/.")
    parser.add_argument("--env-name", default=DEFAULT_ENV_NAME, help="pixi global environment name.")
    parser.add_argument("--env-prefix", type=Path, help="Installed environment prefix, used for Python-binding tests.")
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
            "xschem": run_xschem_upstream(source_path(args.xschem_source), work_dir, args.profile, args.timeout),
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
