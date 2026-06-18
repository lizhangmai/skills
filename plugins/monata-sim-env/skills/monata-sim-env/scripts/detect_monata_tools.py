#!/usr/bin/env python
"""Detect external circuit-tool packages needed by a Monata workspace."""

import argparse
import json
import re
from pathlib import Path


BASELINE_PACKAGES = ["ngspice", "openvaf-r"]
TEXT_SUFFIXES = {".md", ".py", ".toml", ".rst", ".txt"}
SCAN_DIRS = ("src", "tests", "docs")
SCAN_FILES = ("pyproject.toml", "README.md")
MAX_FILE_BYTES = 500_000


def read_text(path):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def candidate_files(root):
    files = []
    for name in SCAN_FILES:
        path = root / name
        if path.is_file():
            files.append(path)
    for dirname in SCAN_DIRS:
        directory = root / dirname
        if directory.is_dir():
            files.extend(
                path
                for path in directory.rglob("*")
                if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES
            )
    return sorted(set(files))


def pyproject_name(root):
    text = read_text(root / "pyproject.toml")
    if not text:
        return None
    match = re.search(r'(?m)^\s*name\s*=\s*["\']([^"\']+)["\']', text)
    if match:
        return match.group(1).strip()
    return None


def detect(root):
    root = root.resolve()
    files = candidate_files(root)
    haystack_parts = []
    evidence = []
    for path in files:
        text = read_text(path)
        if not text:
            continue
        lower = text.lower()
        relative = str(path.relative_to(root))
        haystack_parts.append(lower)
        if "ngspice" in lower:
            evidence.append(f"{relative}: ngspice")
        if "openvaf" in lower or "osdi" in lower or "modelcompiler" in lower:
            evidence.append(f"{relative}: OpenVAF/OSDI")

    haystack = "\n".join(haystack_parts)
    is_monata = (
        pyproject_name(root) == "monata"
        or (root / "src" / "monata").is_dir()
        or "monata" in haystack
    )

    packages = list(BASELINE_PACKAGES) if is_monata else []
    reasons = []
    if is_monata:
        reasons.append("Monata baseline environment currently uses ngspice plus OpenVAF/OSDI tooling.")
    if "xycerunner" in haystack or (root / "src" / "monata" / "sim" / "backends" / "xyce.py").exists():
        packages.append("xyce")
        reasons.append("Active Xyce backend evidence was found.")

    if not packages:
        packages = list(BASELINE_PACKAGES)
        reasons.append("No Monata workspace was detected; using the Monata baseline package set.")

    return {
        "root": str(root),
        "packages": sorted(set(packages), key=packages.index),
        "pixi_dependencies": sorted(set(packages), key=packages.index),
        "checks": sorted(set(packages), key=packages.index),
        "evidence": evidence[:20],
        "reasons": reasons,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Workspace root to inspect.")
    parser.add_argument(
        "--format",
        choices=("json", "shell"),
        default="json",
        help="Print JSON metadata or a shell-friendly package list.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    result = detect(args.root)
    if args.format == "shell":
        print(" ".join(result["packages"]))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
