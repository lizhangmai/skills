#!/usr/bin/env python
"""Compatibility wrapper for the monata-env isolated skill container runner."""

import runpy
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "skill_container.py"


def main():
    if "--repo-root" not in sys.argv:
        sys.argv[1:1] = ["--repo-root", str(REPO_ROOT)]
    runpy.run_path(str(RUNNER), run_name="__main__")


if __name__ == "__main__":
    main()
