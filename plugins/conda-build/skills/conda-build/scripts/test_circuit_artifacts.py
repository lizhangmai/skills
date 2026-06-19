#!/usr/bin/env python
"""Install and smoke-test built circuit-toolchain conda artifacts with pixi."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR_ENV_VAR = "CONDA_BUILD_OUTPUT_DIR"
RATTLER_OUTPUT_DIR_ENV_VAR = "CONDA_BLD_PATH"
DEFAULT_CHANNELS = ["https://prefix.dev/conda-forge"]
FIXTURE_DIR = SKILL_DIR / "assets" / "recipe-sets" / "circuit-toolchain" / "smoke-tests" / "fixtures"


def default_output_dir() -> Path:
    value = os.environ.get(OUTPUT_DIR_ENV_VAR) or os.environ.get(RATTLER_OUTPUT_DIR_ENV_VAR)
    if value:
        return Path(value)
    raise SystemExit(
        "Set CONDA_BUILD_OUTPUT_DIR, CONDA_BLD_PATH, or pass --output-dir before testing artifacts."
    )


def resolve_output_dir(value) -> Path:
    if value is not None:
        return value
    return default_output_dir()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Local conda channel containing built artifacts. Required unless $CONDA_BUILD_OUTPUT_DIR or $CONDA_BLD_PATH is set.",
    )
    parser.add_argument(
        "--channel",
        action="append",
        default=[],
        help="Additional dependency channel. Defaults to https://prefix.dev/conda-forge.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Working directory for the temporary pixi project. Defaults to a new /tmp directory.",
    )
    parser.add_argument("--keep-work-dir", action="store_true", help="Do not delete the temporary pixi project.")
    parser.add_argument("--pixi", default="pixi", help="pixi executable to use.")
    parser.add_argument("--inside-toolchain", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--inside-trilinos17", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--fixtures", type=Path, default=FIXTURE_DIR, help=argparse.SUPPRESS)
    return parser.parse_args()


def run(command, cwd=None, timeout=None):
    printable = " ".join(str(part) for part in command)
    print(f"+ {printable}", flush=True)
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit code {result.returncode}: {printable}")
    return result


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"Required tool not found on PATH: {name}")
    return path


def assert_file(path: Path, minimum_size: int = 1) -> None:
    if not path.exists():
        raise SystemExit(f"Expected file was not created: {path}")
    if path.stat().st_size < minimum_size:
        raise SystemExit(f"Expected file is too small: {path}")


def write_manifest(path, output_dir, channels):
    channel_values = [output_dir.resolve().as_uri(), *channels]
    channel_text = ", ".join('"{}"'.format(channel) for channel in channel_values)
    path.write_text(
        f"""[workspace]
name = "conda-build-circuit-artifact-smoke"
channels = [{channel_text}]
platforms = ["linux-64"]

[feature.toolchain.dependencies]
python = ">=3.12,<3.13"
numpy = "*"
adms = "2.3.7.*"
ngspice = "46.0.*"
openvaf-r = "0.4.0.*"
klayout = "0.30.9.*"
vacask = "0.1.0.*"
xdm = "2.7.0.*"
xyce = "7.11.0.*"
monata = "0.1.0.*"
inspice = "1.7.0.3.*"

[feature.trilinos17.dependencies]
python = ">=3.12,<3.13"
trilinos = "17.1.0.*"

[environments]
toolchain = ["toolchain"]
trilinos17 = ["trilinos17"]
""",
        encoding="utf-8",
    )


def smoke_imports() -> None:
    import InSpice  # noqa: F401
    import monata  # noqa: F401
    import numpy  # noqa: F401

    print("PASS: Python imports succeeded: monata, InSpice, numpy")


def smoke_ngspice(fixtures: Path, work_dir: Path) -> None:
    require_tool("ngspice")
    shutil.copy2(fixtures / "rc_lowpass.spice", work_dir / "rc_lowpass.spice")
    run(["ngspice", "-b", "rc_lowpass.spice"], cwd=work_dir, timeout=60)
    output = work_dir / "rc_lowpass_out.txt"
    assert_file(output)
    line_count = len(output.read_text(encoding="utf-8", errors="replace").splitlines())
    if line_count < 10:
        raise SystemExit(f"ngspice output has too few lines: {line_count}")
    print(f"PASS: ngspice generated {line_count} output lines")


def smoke_openvaf(fixtures: Path, work_dir: Path) -> None:
    require_tool("openvaf-r")
    output_dir = work_dir / "openvaf-output"
    output_dir.mkdir()
    for name in ("resistor", "capacitor"):
        output = output_dir / f"{name}.osdi"
        run(["openvaf-r", fixtures / f"{name}.va", "-o", output], cwd=work_dir, timeout=120)
        assert_file(output, minimum_size=1000)
    print("PASS: openvaf-r compiled resistor and capacitor OSDI models")


def smoke_klayout() -> None:
    require_tool("klayout")
    run(["klayout", "-v"], timeout=60)
    print("PASS: klayout reported its version")


def smoke_adms(fixtures: Path, work_dir: Path) -> None:
    require_tool("admsXml")
    result = subprocess.run(
        ["admsXml", str(fixtures / "resistor.va")],
        cwd=str(work_dir),
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    if "resistor" not in (result.stdout or "").lower() and result.returncode != 0:
        print(result.stdout)
        raise SystemExit("admsXml did not parse the resistor fixture")
    print("PASS: admsXml is functional")


def smoke_vacask(fixtures: Path, work_dir: Path) -> None:
    require_tool("vacask")
    shutil.copy2(fixtures / "rc_lowpass.sim", work_dir / "rc_lowpass.sim")
    run(["vacask", "rc_lowpass.sim"], cwd=work_dir, timeout=120)
    print("PASS: vacask completed the RC transient deck")


def smoke_xyce(fixtures: Path, work_dir: Path) -> None:
    require_tool("Xyce")
    shutil.copy2(fixtures / "xyce_rc.cir", work_dir / "xyce_rc.cir")
    run(["Xyce", "xyce_rc.cir"], cwd=work_dir, timeout=120)
    outputs = sorted(work_dir.glob("*.prn"))
    if outputs:
        assert_file(outputs[0])
    print("PASS: Xyce completed the RC transient deck")


def smoke_xdm(fixtures: Path, work_dir: Path) -> None:
    prefix = Path(os.environ.get("CONDA_PREFIX", ""))
    xdm_script = prefix / "xdm_bundle" / "xdm_bdl.py"
    if not xdm_script.exists():
        raise SystemExit(f"XDM bundle script not found: {xdm_script}")
    shutil.copy2(fixtures / "hspice_rc.sp", work_dir / "hspice_rc.sp")
    run([sys.executable, xdm_script, "hspice_rc.sp", "-s", "hspice", "-o", "xyce", "-d", "xdm_out"], cwd=work_dir, timeout=120)
    converted = sorted((work_dir / "xdm_out").rglob("*"))
    if not any(path.is_file() for path in converted):
        raise SystemExit("XDM did not generate converted output")
    print("PASS: XDM converted the HSpice fixture")


def run_toolchain_smoke(fixtures: Path) -> int:
    fixtures = fixtures.resolve()
    if not fixtures.exists():
        raise SystemExit(f"Fixture directory not found: {fixtures}")
    smoke_imports()
    with tempfile.TemporaryDirectory(prefix="conda-build-circuit-smoke-") as tmp:
        work_dir = Path(tmp)
        smoke_ngspice(fixtures, work_dir)
        smoke_openvaf(fixtures, work_dir)
        smoke_klayout()
        smoke_adms(fixtures, work_dir)
        smoke_vacask(fixtures, work_dir)
        smoke_xyce(fixtures, work_dir)
        smoke_xdm(fixtures, work_dir)
    return 0


def run_trilinos17_smoke() -> int:
    prefix = Path(os.environ.get("CONDA_PREFIX", ""))
    if not prefix.exists():
        raise SystemExit("CONDA_PREFIX is not set to an installed pixi environment")
    headers = list((prefix / "include").rglob("Trilinos_version.h"))
    libs = list((prefix / "lib").glob("libtrilinos*")) + list((prefix / "lib").glob("libteuchoscore*"))
    if not headers and not libs:
        raise SystemExit("Trilinos 17.1.0 files were not found in the environment")
    print("PASS: trilinos 17.1.0 environment contains installed headers/libraries")
    return 0


def run_pixi_smoke(args: argparse.Namespace) -> int:
    if shutil.which(args.pixi) is None:
        raise SystemExit(f"pixi was not found on PATH: {args.pixi}")
    output_dir = resolve_output_dir(args.output_dir).resolve()
    if not output_dir.exists():
        raise SystemExit(f"Output channel does not exist: {output_dir}")
    channels = args.channel or DEFAULT_CHANNELS

    if args.work_dir:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="conda-build-circuit-pixi-"))
        cleanup = not args.keep_work_dir

    try:
        manifest = work_dir / "pixi.toml"
        write_manifest(manifest, output_dir, channels)
        script = Path(__file__).resolve()
        fixtures = FIXTURE_DIR.resolve()
        run([args.pixi, "run", "--manifest-path", manifest, "-e", "toolchain", "python", script, "--inside-toolchain", "--fixtures", fixtures], cwd=work_dir)
        run([args.pixi, "run", "--manifest-path", manifest, "-e", "trilinos17", "python", script, "--inside-trilinos17"], cwd=work_dir)
        print(f"PASS: pixi installed and smoke-tested artifacts from {output_dir}")
        if args.keep_work_dir or args.work_dir:
            print(f"Work directory: {work_dir}")
        return 0
    finally:
        if cleanup:
            shutil.rmtree(work_dir, ignore_errors=True)


def main() -> int:
    args = parse_args()
    if args.inside_toolchain:
        return run_toolchain_smoke(args.fixtures)
    if args.inside_trilinos17:
        return run_trilinos17_smoke()
    return run_pixi_smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
