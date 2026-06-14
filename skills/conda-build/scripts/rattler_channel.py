#!/usr/bin/env python3
"""Thin helpers for local conda channels managed with rattler-build."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
RECIPE_SET_ROOT = SKILL_DIR / "assets" / "recipe-sets"
DEFAULT_RECIPE_SET = "circuit-toolchain"
OUTPUT_DIR_ENV_VAR = "CONDA_BUILD_OUTPUT_DIR"
RATTLER_OUTPUT_DIR_ENV_VAR = "CONDA_BLD_PATH"
DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "lizhangmai-conda-channel"
DEFAULT_CHANNELS = ["https://prefix.dev/conda-forge"]

BUILD_ORDERS = {
    "circuit-toolchain": [
        "boost",
        "adms",
        "trilinos-14.4.0",
        "ngspice",
        "openvaf-r",
        "xdm",
        "inspice",
        "monata",
        "vacask",
        "xyce",
        "trilinos-17.1.0",
    ],
}
PACKAGE_ALIASES = {
    "circuit-toolchain": {
        "trilinos": "trilinos-14.4.0",
        "trilinos14": "trilinos-14.4.0",
        "trilinos17": "trilinos-17.1.0",
    },
}


def recipe_sets():
    if not RECIPE_SET_ROOT.exists():
        return []
    return sorted(
        path.name
        for path in RECIPE_SET_ROOT.iterdir()
        if path.is_dir() and (path / "recipes").is_dir()
    )


def recipe_dir(recipe_set):
    path = RECIPE_SET_ROOT / recipe_set / "recipes"
    if not path.is_dir():
        raise SystemExit("Unknown recipe set: {}".format(recipe_set))
    return path


def available_packages(recipe_set):
    root = recipe_dir(recipe_set)
    return sorted(path.name for path in root.iterdir() if (path / "recipe.yaml").exists())


def normalize_package(recipe_set, name):
    return PACKAGE_ALIASES.get(recipe_set, {}).get(name, name)


def ordered_packages(recipe_set, selected):
    if not selected:
        return []
    selected_set = set(normalize_package(recipe_set, name) for name in selected)
    order = BUILD_ORDERS.get(recipe_set, [])
    ordered = [name for name in order if name in selected_set]
    ordered.extend(sorted(selected_set - set(ordered)))
    return ordered


def output_package_names(root, package_dirs):
    names = set()
    for package_dir in package_dirs:
        recipe = root / package_dir / "recipe.yaml"
        lines = recipe.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if line.strip() == "package:":
                for package_line in lines[index + 1 :]:
                    stripped = package_line.strip()
                    if stripped.startswith("name:"):
                        names.add(stripped.split(":", 1)[1].strip().strip("\"'"))
                        break
                    if package_line and not package_line.startswith(" "):
                        break
                break
    return names


def run(command, dry_run=False, env=None):
    print("+ " + " ".join(str(part) for part in command), flush=True)
    if not dry_run:
        subprocess.run([str(part) for part in command], check=True, env=env)


def env_output_dir():
    value = os.environ.get(OUTPUT_DIR_ENV_VAR) or os.environ.get(RATTLER_OUTPUT_DIR_ENV_VAR)
    if value:
        return Path(value)
    return None


def resolve_output_dir(value, remind=False):
    if value is not None:
        return Path(value)
    env_value = env_output_dir()
    if env_value is not None:
        return env_value
    if remind:
        print(
            "NOTICE: set {}={} before building "
            "to choose the final artifact channel. Using default: {}".format(
                OUTPUT_DIR_ENV_VAR,
                DEFAULT_OUTPUT_DIR,
                DEFAULT_OUTPUT_DIR,
            ),
            flush=True,
        )
    return DEFAULT_OUTPUT_DIR


def require_rattler_build(args):
    if not getattr(args, "dry_run", False) and shutil.which(args.rattler_build) is None:
        raise SystemExit("rattler-build was not found on PATH: {}".format(args.rattler_build))


def add_common_options(parser):
    parser.add_argument(
        "--rattler-build",
        default="rattler-build",
        help="rattler-build executable to use.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")


def add_channel_options(parser):
    parser.add_argument(
        "--channel",
        action="append",
        default=[],
        help="Dependency channel. Defaults to https://prefix.dev/conda-forge when omitted.",
    )


def add_extra_options(parser):
    parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra raw argument passed to rattler-build. Repeat for multiple arguments.",
    )


def extend_channels(command, channels):
    for channel in channels or DEFAULT_CHANNELS:
        command.extend(["--channel", channel])


def extend_extra_args(command, args):
    for value in getattr(args, "extra_arg", []) or []:
        command.append(value)


def build_environment(args):
    if args.jobs is None:
        return None
    if args.jobs < 1:
        raise SystemExit("--jobs must be a positive integer")
    env = os.environ.copy()
    env["CPU_COUNT"] = str(args.jobs)
    return env


def base_build_command(args):
    args.output_dir = resolve_output_dir(args.output_dir, remind=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    command = [args.rattler_build, "build", "--output-dir", args.output_dir]
    extend_channels(command, args.channel)
    if args.render_only:
        command.append("--render-only")
    if args.with_solve:
        command.append("--with-solve")
    for value in args.variant or []:
        command.extend(["--variant", value])
    for value in args.variant_config or []:
        command.extend(["--variant-config", value])
    if args.test:
        command.extend(["--test", args.test])
    if args.sandbox:
        command.append("--sandbox")
    if args.allow_network:
        command.append("--allow-network")
    if args.skip_existing:
        command.append("--skip-existing")
    extend_extra_args(command, args)
    return command


def cmd_list_recipe_sets(args):
    del args
    for name in recipe_sets():
        print(name)
    return 0


def cmd_list_recipes(args):
    for package in available_packages(args.recipe_set):
        print(package)
    return 0


def cmd_build(args):
    require_rattler_build(args)
    env = build_environment(args)
    selected_paths = [path.resolve() for path in args.recipe_path or []]

    if args.recipe_path:
        if args.all or args.up_to or args.package:
            raise SystemExit("--recipe-path cannot be combined with --package, --all, or --up-to")
        for path in selected_paths:
            command = base_build_command(args)
            command.extend(["--recipe", path])
            run(command, dry_run=args.dry_run, env=env)
        return 0

    root = recipe_dir(args.recipe_set)
    packages = available_packages(args.recipe_set)

    if args.up_to:
        targets = output_package_names(root, packages)
        if args.up_to not in targets:
            raise SystemExit("Unknown package output for --up-to: {}".format(args.up_to))
        command = base_build_command(args)
        command.extend(["--recipe-dir", root, "--up-to", args.up_to])
        run(command, dry_run=args.dry_run, env=env)
        return 0

    selected = packages if args.all else ordered_packages(args.recipe_set, args.package)
    if not selected:
        raise SystemExit("Pass --package <name>, --all, --up-to <name>, or --recipe-path <path>.")

    unknown = sorted(set(selected) - set(packages))
    if unknown:
        raise SystemExit("Unknown package(s): {}".format(", ".join(unknown)))

    for package in ordered_packages(args.recipe_set, selected):
        command = base_build_command(args)
        command.extend(["--recipe", root / package])
        run(command, dry_run=args.dry_run, env=env)
    return 0


def cmd_test_package(args):
    require_rattler_build(args)
    command = [args.rattler_build, "test", "--package-file", args.package_file]
    extend_channels(command, args.channel)
    if args.output_dir:
        command.extend(["--output-dir", args.output_dir])
    extend_extra_args(command, args)
    run(command, dry_run=args.dry_run)
    return 0


def cmd_inspect_package(args):
    require_rattler_build(args)
    command = [args.rattler_build, "package", "inspect"]
    for flag in ("paths", "about", "run_exports", "all", "json"):
        if getattr(args, flag):
            command.append("--{}".format(flag.replace("_", "-")))
    command.append(args.package_file)
    run(command, dry_run=args.dry_run)
    return 0


def cmd_extract_package(args):
    require_rattler_build(args)
    command = [args.rattler_build, "package", "extract", args.package_file]
    if args.dest:
        command.extend(["--dest", args.dest])
    run(command, dry_run=args.dry_run)
    return 0


def cmd_rebuild(args):
    require_rattler_build(args)
    args.output_dir = resolve_output_dir(args.output_dir, remind=True)
    command = [args.rattler_build, "rebuild", "--package-file", args.package_file, "--output-dir", args.output_dir]
    if args.test:
        command.extend(["--test", args.test])
    extend_extra_args(command, args)
    run(command, dry_run=args.dry_run)
    return 0


def cmd_generate_recipe(args):
    require_rattler_build(args)
    command = [args.rattler_build, "generate-recipe", args.ecosystem, args.name]
    extend_extra_args(command, args)
    run(command, dry_run=args.dry_run)
    return 0


def cmd_bump_recipe(args):
    require_rattler_build(args)
    command = [args.rattler_build, "bump-recipe", "--recipe", args.recipe]
    if args.version:
        command.extend(["--version", args.version])
    if args.check_only:
        command.append("--check-only")
    if args.keep_build_number:
        command.append("--keep-build-number")
    extend_extra_args(command, args)
    run(command, dry_run=args.dry_run)
    return 0


def cmd_rattler(args):
    require_rattler_build(args)
    raw_args = list(args.args)
    if raw_args and raw_args[0] == "--":
        raw_args = raw_args[1:]
    if not raw_args:
        raise SystemExit("Pass rattler-build arguments after 'rattler --'.")
    run([args.rattler_build] + raw_args, dry_run=args.dry_run)
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    list_sets = subparsers.add_parser("list-recipe-sets", help="List bundled recipe sets.")
    list_sets.set_defaults(func=cmd_list_recipe_sets)

    list_recipes = subparsers.add_parser("list-recipes", help="List recipes in a bundled recipe set.")
    list_recipes.add_argument("--recipe-set", default=DEFAULT_RECIPE_SET, help="Bundled recipe set to inspect.")
    list_recipes.set_defaults(func=cmd_list_recipes)

    build = subparsers.add_parser("build", help="Build or render bundled or custom recipes.")
    build.add_argument("--recipe-set", default=DEFAULT_RECIPE_SET, help="Bundled recipe set to use.")
    build.add_argument("--package", action="append", help="Bundled recipe to build. Repeat for multiple packages.")
    build.add_argument("--all", action="store_true", help="Build all recipes in dependency order.")
    build.add_argument("--up-to", help="Build a bundled recipe dependency set via rattler-build --recipe-dir.")
    build.add_argument("--recipe-path", action="append", type=Path, help="Custom recipe directory or recipe.yaml path.")
    build.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Directory for built conda packages. Defaults to ${}, then ${}, then {}."
        ).format(OUTPUT_DIR_ENV_VAR, RATTLER_OUTPUT_DIR_ENV_VAR, DEFAULT_OUTPUT_DIR),
    )
    build.add_argument("--render-only", action="store_true", help="Render recipes without executing builds.")
    build.add_argument("--with-solve", action="store_true", help="Solve rendered dependencies during render-only analysis.")
    build.add_argument("--variant", action="append", help="Variant override passed to rattler-build.")
    build.add_argument("--variant-config", action="append", type=Path, help="Variant config file passed to rattler-build.")
    build.add_argument(
        "--test",
        choices=["skip", "native", "native-and-emulated"],
        help="rattler-build build --test mode.",
    )
    build.add_argument("--sandbox", action="store_true", help="Enable rattler-build sandboxing.")
    build.add_argument("--allow-network", action="store_true", help="Allow network access inside sandboxed builds.")
    build.add_argument("--skip-existing", action="store_true", help="Skip packages that already exist in the output channel.")
    build.add_argument("--jobs", type=int, help="Set CPU_COUNT for recipe build scripts.")
    add_channel_options(build)
    add_extra_options(build)
    add_common_options(build)
    build.set_defaults(func=cmd_build)

    test_pkg = subparsers.add_parser("test-package", help="Run rattler-build test on an existing package.")
    test_pkg.add_argument("--package-file", type=Path, required=True, help="Existing .conda or .tar.bz2 package file.")
    test_pkg.add_argument("--output-dir", type=Path, help="Temporary output directory used by rattler-build test.")
    add_channel_options(test_pkg)
    add_extra_options(test_pkg)
    add_common_options(test_pkg)
    test_pkg.set_defaults(func=cmd_test_package)

    inspect_pkg = subparsers.add_parser("inspect-package", help="Inspect a built conda package.")
    inspect_pkg.add_argument("--package-file", type=Path, required=True, help="Existing .conda or .tar.bz2 package file.")
    inspect_pkg.add_argument("--paths", action="store_true", help="Show detailed file listing.")
    inspect_pkg.add_argument("--about", action="store_true", help="Show about metadata.")
    inspect_pkg.add_argument("--run-exports", action="store_true", help="Show run_exports.")
    inspect_pkg.add_argument("--all", action="store_true", help="Show all available metadata.")
    inspect_pkg.add_argument("--json", action="store_true", help="Print JSON output.")
    add_common_options(inspect_pkg)
    inspect_pkg.set_defaults(func=cmd_inspect_package)

    extract_pkg = subparsers.add_parser("extract-package", help="Extract a built conda package.")
    extract_pkg.add_argument("--package-file", type=Path, required=True, help="Existing .conda or .tar.bz2 package file.")
    extract_pkg.add_argument("--dest", type=Path, help="Destination directory.")
    add_common_options(extract_pkg)
    extract_pkg.set_defaults(func=cmd_extract_package)

    rebuild = subparsers.add_parser("rebuild", help="Rebuild a package from saved recipe metadata.")
    rebuild.add_argument("--package-file", type=Path, required=True, help="Existing package to reproduce.")
    rebuild.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Directory for rebuilt packages. Defaults to ${}, then ${}, then {}."
        ).format(OUTPUT_DIR_ENV_VAR, RATTLER_OUTPUT_DIR_ENV_VAR, DEFAULT_OUTPUT_DIR),
    )
    rebuild.add_argument(
        "--test",
        choices=["skip", "native", "native-and-emulated"],
        help="rattler-build rebuild --test mode.",
    )
    add_extra_options(rebuild)
    add_common_options(rebuild)
    rebuild.set_defaults(func=cmd_rebuild)

    generate = subparsers.add_parser("generate-recipe", help="Generate a recipe from an ecosystem package.")
    generate.add_argument("ecosystem", help="Ecosystem, for example pypi, cran, cpan, or luarocks.")
    generate.add_argument("name", help="Package name in that ecosystem.")
    add_extra_options(generate)
    add_common_options(generate)
    generate.set_defaults(func=cmd_generate_recipe)

    bump = subparsers.add_parser("bump-recipe", help="Update a recipe version and checksums.")
    bump.add_argument("--recipe", type=Path, required=True, help="Recipe file or recipe directory.")
    bump.add_argument("--version", help="Target version.")
    bump.add_argument("--check-only", action="store_true", help="Check for updates without modifying the recipe.")
    bump.add_argument("--keep-build-number", action="store_true", help="Do not reset the build number.")
    add_extra_options(bump)
    add_common_options(bump)
    bump.set_defaults(func=cmd_bump_recipe)

    passthrough = subparsers.add_parser("rattler", help="Run a raw rattler-build command.")
    passthrough.add_argument("args", nargs=argparse.REMAINDER, help="Raw arguments, usually after --.")
    add_common_options(passthrough)
    passthrough.set_defaults(func=cmd_rattler)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(2)
    return args


def main():
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
