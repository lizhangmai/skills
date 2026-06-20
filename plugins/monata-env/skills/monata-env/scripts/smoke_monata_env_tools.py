#!/usr/bin/env python
"""Smoke-test monata-env tool commands without importing Monata."""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_TOOLS = ["ngspice", "openvaf-r", "klayout", "xschem"]
RESISTOR_VA = """`include "disciplines.vams"

module resistor(p, n);
    inout p, n;
    electrical p, n;
    parameter real r = 1.0 from (0:inf);

    analog begin
        I(p, n) <+ V(p, n) / r;
    end
endmodule
"""
CAPACITOR_VA = """`include "disciplines.vams"

module capacitor(p, n);
    inout p, n;
    electrical p, n;
    parameter real c = 1e-12 from (0:inf);

    analog begin
        I(p, n) <+ ddt(c * V(p, n));
    end
endmodule
"""


def run(command, cwd=None, timeout=120):
    result = subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=timeout,
    )
    return {
        "command": [str(part) for part in command],
        "returncode": result.returncode,
        "output": result.stdout[-4000:],
    }


def missing_result(tool):
    return {
        "ok": False,
        "reason": "missing",
        "path": "",
        "checks": [],
    }


def tool_path(tool):
    return shutil.which(tool)


def smoke_ngspice(path, work_dir):
    deck = work_dir / "rc.cir"
    deck.write_text(
        """* simple RC operating point
V1 in 0 1
R1 in out 1k
C1 out 0 1p
.op
.print op v(in) v(out)
.end
""",
        encoding="utf-8",
    )
    return [
        run([path, "--version"], timeout=60),
        run([path, "-b", deck], cwd=work_dir, timeout=60),
    ]


def smoke_openvaf(path, work_dir):
    checks = [run([path, "--help"], timeout=60)]
    for name, text in {"resistor": RESISTOR_VA, "capacitor": CAPACITOR_VA}.items():
        source = work_dir / f"{name}.va"
        output = work_dir / f"{name}.osdi"
        source.write_text(text, encoding="utf-8")
        checks.append(run([path, source, "-o", output], cwd=work_dir, timeout=120))
        checks[-1]["output_file"] = str(output)
        checks[-1]["output_size"] = output.stat().st_size if output.exists() else 0
    return checks


def smoke_klayout(path, work_dir):
    ruby_script = work_dir / "klayout-smoke.rb"
    ruby_output = work_dir / "klayout-smoke.gds"
    python_script = work_dir / "klayout-python-smoke.py"
    python_output = work_dir / "klayout-python-smoke.gds"
    ruby_script.write_text(
        f"""layout = RBA::Layout::new
cell = layout.create_cell('TOP')
layer = layout.layer(1, 0)
cell.shapes(layer).insert(RBA::Box::new(0, 0, 1000, 1000))
layout.write('{ruby_output}')
puts 'wrote {ruby_output}'
""",
        encoding="utf-8",
    )
    python_script.write_text(
        f"""import klayout.db as db
layout = db.Layout()
cell = layout.create_cell('TOP')
layer = layout.layer(1, 0)
cell.shapes(layer).insert(db.Box(0, 0, 1000, 1000))
layout.write('{python_output}')
print('wrote {python_output}')
""",
        encoding="utf-8",
    )
    checks = [
        run([path, "-v"], timeout=60),
        run([path, "-b", "-r", ruby_script], cwd=work_dir, timeout=120),
        run([path, "-b", "-r", python_script], cwd=work_dir, timeout=120),
    ]
    checks[-2]["output_file"] = str(ruby_output)
    checks[-2]["output_size"] = ruby_output.stat().st_size if ruby_output.exists() else 0
    checks[-1]["output_file"] = str(python_output)
    checks[-1]["output_size"] = python_output.stat().st_size if python_output.exists() else 0
    return checks


def smoke_xschem(path, work_dir):
    del work_dir
    return [run([path, "--version"], timeout=60)]


SMOKE_HANDLERS = {
    "ngspice": smoke_ngspice,
    "openvaf-r": smoke_openvaf,
    "klayout": smoke_klayout,
    "xschem": smoke_xschem,
}


def smoke_tool(tool, work_dir):
    path = tool_path(tool)
    if path is None:
        return missing_result(tool)
    checks = SMOKE_HANDLERS[tool](path, work_dir)
    ok = all(item["returncode"] == 0 for item in checks)
    return {
        "ok": ok,
        "reason": "ok" if ok else "command-failed",
        "path": path,
        "checks": checks,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool", action="append", choices=DEFAULT_TOOLS, help="Tool to test. Repeat for multiple tools.")
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    parser.add_argument("--work-dir", type=Path, help="Working directory for generated smoke files.")
    parser.add_argument("--keep-work-dir", action="store_true", help="Keep an auto-created work directory.")
    return parser.parse_args()


def run_smoke(args):
    tools = args.tool or DEFAULT_TOOLS
    cleanup = None
    if args.work_dir:
        work_dir = args.work_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="monata-env-smoke-")
        work_dir = Path(cleanup.name)
    try:
        results = {tool: smoke_tool(tool, work_dir) for tool in tools}
        return {
            "ok": all(item["ok"] for item in results.values()),
            "work_dir": str(work_dir),
            "tools": results,
        }
    finally:
        if cleanup is not None and not args.keep_work_dir:
            cleanup.cleanup()


def print_summary(report):
    for tool, result in report["tools"].items():
        status = "PASS" if result["ok"] else "FAIL"
        print(f"{status} {tool}: {result['reason']}")


def main():
    args = parse_args()
    report = run_smoke(args)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
