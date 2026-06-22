#!/usr/bin/env python
"""Audit monata-env planner pins against circuit-toolchain recipes."""

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_PINS_FILE = SKILL_ROOT / "references" / "circuit-tool-pins.json"
DEFAULT_PLANNER_SCRIPT = SCRIPT_DIR / "plan_monata_env.py"
DEFAULT_RECIPE_ROOT = (
    SCRIPT_DIR.parents[3]
    / "conda-build"
    / "skills"
    / "conda-build"
    / "assets"
    / "recipe-sets"
    / "circuit-toolchain"
    / "recipes"
)
CHECKS = [
    "planner-source-ref",
    "planner-package-spec",
    "recipe-version",
    "recipe-source-commit",
    "recipe-sha256",
]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pins-file", type=Path, default=DEFAULT_PINS_FILE)
    parser.add_argument("--planner-script", type=Path, default=DEFAULT_PLANNER_SCRIPT)
    parser.add_argument("--recipe-root", type=Path, default=DEFAULT_RECIPE_ROOT)
    parser.add_argument("--format", choices=["summary", "json"], default="summary")
    return parser.parse_args(argv)


def load_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_planner_constants(path):
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location("monata_env_plan_for_pin_audit", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {
            "expected_source_refs": dict(module.EXPECTED_SOURCE_REFS),
            "pixi_package_specs": dict(module.PIXI_PACKAGE_SPECS),
        }
    finally:
        try:
            sys.path.remove(str(path.parent))
        except ValueError:
            pass


def clean_scalar(value):
    value = value.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]
    return value


def parse_recipe(path):
    data = {}
    section = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")) and line.rstrip().endswith(":"):
            section = line.strip()[:-1]
            continue
        if section not in {"package", "source"}:
            continue
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if key in {"name", "version", "url", "sha256"}:
            data[f"{section}.{key}"] = clean_scalar(value)
    return {
        "name": data.get("package.name"),
        "version": data.get("package.version"),
        "source_url": data.get("source.url"),
        "sha256": data.get("source.sha256"),
    }


def add_error(errors, package, check, expected, actual, path=None):
    error = {
        "package": package,
        "check": check,
        "expected": expected,
        "actual": actual,
    }
    if path is not None:
        error["path"] = str(path)
    errors.append(error)


def package_record(package, pin, planner, recipe):
    return {
        "version": pin["version"],
        "source_ref": pin["source_ref"],
        "source_commit": pin["source_commit"],
        "planner_package_spec": planner["pixi_package_specs"].get(package),
        "recipe_version": recipe.get("version"),
        "recipe_source_url": recipe.get("source_url"),
        "recipe_sha256": recipe.get("sha256"),
        "checks": CHECKS,
    }


def audit(args):
    pins_file = args.pins_file.expanduser().resolve()
    planner_script = args.planner_script.expanduser().resolve()
    recipe_root = args.recipe_root.expanduser().resolve()
    pins = load_json(pins_file)
    planner = load_planner_constants(planner_script)
    errors = []
    packages = {}

    for package, pin in sorted(pins["packages"].items()):
        recipe_path = recipe_root / package / "recipe.yaml"
        recipe = parse_recipe(recipe_path) if recipe_path.exists() else {}
        packages[package] = package_record(package, pin, planner, recipe)

        actual_ref = planner["expected_source_refs"].get(package)
        if actual_ref != pin["source_ref"]:
            add_error(errors, package, "planner-source-ref", pin["source_ref"], actual_ref, planner_script)

        actual_spec = planner["pixi_package_specs"].get(package)
        if actual_spec != pin["planner_package_spec"]:
            add_error(errors, package, "planner-package-spec", pin["planner_package_spec"], actual_spec, planner_script)

        if recipe.get("version") != pin["version"]:
            add_error(errors, package, "recipe-version", pin["version"], recipe.get("version"), recipe_path)

        source_url = recipe.get("source_url") or ""
        if pin["source_commit"] not in source_url:
            add_error(errors, package, "recipe-source-commit", pin["source_commit"], source_url, recipe_path)

        sha256 = recipe.get("sha256")
        expected_sha256 = pin["recipe_sha256"]
        if sha256 != expected_sha256 or not isinstance(sha256, str) or SHA256_RE.match(sha256) is None:
            add_error(errors, package, "recipe-sha256", expected_sha256, sha256, recipe_path)

    return {
        "ok": not errors,
        "pins_file": str(pins_file),
        "planner_script": str(planner_script),
        "recipe_root": str(recipe_root),
        "packages": packages,
        "errors": errors,
    }


def print_summary(result):
    if result["ok"]:
        package_names = " ".join(result["packages"])
        print(f"ok: audited recipe pins for {package_names}")
        return
    print("recipe pin audit failed:", file=sys.stderr)
    for error in result["errors"]:
        print(
            f"- {error['package']} {error['check']}: expected {error['expected']!r}, got {error['actual']!r}",
            file=sys.stderr,
        )


def main(argv=None):
    args = parse_args(argv)
    result = audit(args)
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_summary(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
