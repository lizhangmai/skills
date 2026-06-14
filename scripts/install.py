#!/usr/bin/env python3
"""Install skills from this repository into local agent skill directories."""

import argparse
import os
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"


def codex_home():
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()


def target_roots(target):
    mapping = {
        "codex": [codex_home() / "skills"],
        "agents": [Path(os.environ.get("AGENTS_HOME", Path.home() / ".agents")).expanduser() / "skills"],
        "claude": [Path.home() / ".claude" / "skills"],
        "both": [codex_home() / "skills", Path.home() / ".claude" / "skills"],
        "all": [
            codex_home() / "skills",
            Path(os.environ.get("AGENTS_HOME", Path.home() / ".agents")).expanduser() / "skills",
            Path.home() / ".claude" / "skills",
        ],
    }
    return mapping[target]


def available_skills():
    if not SKILLS_DIR.exists():
        return []
    return sorted(path.name for path in SKILLS_DIR.iterdir() if (path / "SKILL.md").exists())


def remove_existing(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def install_skill(skill, root, mode, force):
    source = SKILLS_DIR / skill
    if not (source / "SKILL.md").exists():
        raise SystemExit(f"Unknown skill: {skill}")

    root.mkdir(parents=True, exist_ok=True)
    destination = root / skill

    if destination.exists() or destination.is_symlink():
        if destination.is_symlink() and destination.resolve() == source.resolve():
            print(f"Already installed: {destination} -> {source}")
            return
        if not force:
            raise SystemExit(f"Destination exists, rerun with --force to replace: {destination}")
        remove_existing(destination)

    if mode == "symlink":
        destination.symlink_to(source.resolve(), target_is_directory=True)
        print(f"Linked {destination} -> {source.resolve()}")
    else:
        shutil.copytree(source, destination)
        print(f"Copied {source} -> {destination}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List available skills and exit.")
    parser.add_argument("--skill", action="append", help="Skill name to install. Repeat for multiple skills.")
    parser.add_argument("--all-skills", action="store_true", help="Install every skill in this repository.")
    parser.add_argument(
        "--target",
        choices=["codex", "agents", "claude", "both", "all"],
        default="codex",
        help="Local agent skill directory to install into.",
    )
    parser.add_argument(
        "--mode",
        choices=["copy", "symlink"],
        default="copy",
        help="Copy skill files or symlink to this repository.",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing installed skill directory.")
    return parser.parse_args()


def main():
    args = parse_args()
    skills = available_skills()

    if args.list:
        for skill in skills:
            print(skill)
        return 0

    selected = skills if args.all_skills else args.skill
    if not selected:
        raise SystemExit("Pass --skill <name>, --all-skills, or --list.")

    unknown = sorted(set(selected) - set(skills))
    if unknown:
        raise SystemExit(f"Unknown skill(s): {', '.join(unknown)}")

    for root in target_roots(args.target):
        for skill in selected:
            install_skill(skill, root, args.mode, args.force)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
