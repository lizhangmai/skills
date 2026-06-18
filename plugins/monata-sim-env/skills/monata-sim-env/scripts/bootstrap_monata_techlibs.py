#!/usr/bin/env python
"""Bootstrap Monata PTM techlibs from the monata-sim-env skill."""

import argparse
import os
import subprocess
import sys
import urllib.request
from pathlib import Path


DEFAULT_MONATA_HOME = "~/.monata"
RAW_INSTALLER_URL = (
    "https://raw.githubusercontent.com/lizhangmai/skills/main/"
    "plugins/monata-techlib/skills/monata-techlib/scripts/install_monata_techlib.py"
)


def expand_path(value):
    return Path(value).expanduser().resolve()


def candidate_installers():
    script_path = Path(__file__).resolve()
    for parent in script_path.parents:
        yield parent / "plugins" / "monata-techlib" / "skills" / "monata-techlib" / "scripts" / "install_monata_techlib.py"
        yield parent / "monata-techlib" / "skills" / "monata-techlib" / "scripts" / "install_monata_techlib.py"


def download_installer(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(RAW_INSTALLER_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    if not data or not data.startswith(b"#!/usr/bin/env python"):
        raise SystemExit("downloaded monata-techlib installer did not look like the expected Python script")
    target.write_bytes(data)
    return target


def resolve_installer(monata_home, explicit=None, refresh=False):
    if explicit:
        path = expand_path(explicit)
        if not path.is_file():
            raise SystemExit("monata-techlib installer does not exist: {}".format(path))
        return path

    for path in candidate_installers():
        if path.is_file():
            return path

    cached = monata_home / "downloads" / "skills" / "monata-techlib" / "install_monata_techlib.py"
    if refresh or not cached.is_file():
        print("Downloading monata-techlib helper script: {}".format(RAW_INSTALLER_URL))
        download_installer(cached)
    else:
        print("Reusing cached monata-techlib helper script: {}".format(cached))
    return cached


def run(command):
    print("+ " + " ".join(str(part) for part in command), flush=True)
    subprocess.run([str(part) for part in command], check=True)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monata-home", help="Monata home directory. Defaults to MONATA_HOME or ~/.monata.")
    parser.add_argument("--cache-dir", help="PTM download/staging cache directory.")
    parser.add_argument("--techlib", action="append", choices=["PTM_MG", "PTM_BULK"], help="Techlib to bootstrap.")
    parser.add_argument("--force", action="store_true", help="Refresh installed techlibs.")
    parser.add_argument("--stage-only", action="store_true", help="Download and generate without installing.")
    parser.add_argument("--installer", help="Explicit install_monata_techlib.py path.")
    parser.add_argument("--refresh-helper", action="store_true", help="Redownload the cached helper script.")
    return parser.parse_args()


def main():
    args = parse_args()
    monata_home = expand_path(args.monata_home or os.environ.get("MONATA_HOME", DEFAULT_MONATA_HOME))
    installer = resolve_installer(monata_home, explicit=args.installer, refresh=args.refresh_helper)

    command = [sys.executable, installer, "bootstrap-ptm", "--monata-home", monata_home]
    if args.cache_dir:
        command.extend(["--cache-dir", expand_path(args.cache_dir)])
    for techlib in args.techlib or []:
        command.extend(["--techlib", techlib])
    if args.force:
        command.append("--force")
    if args.stage_only:
        command.append("--stage-only")

    run(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
