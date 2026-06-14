#!/usr/bin/env python3
"""Validate the multi-skill repository structure."""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKETPLACE_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_PUBLIC_TOKENS = [
    "/" + "workspace" + "/",
    "/" + "share" + "/personal" + "/",
    "lizhangmai" + "-skills",
    "github.com/lizhangmai/" + "lizhangmai" + "-skills",
]


def parse_frontmatter(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        end = lines[1:].index("---") + 1
    except ValueError as exc:
        raise ValueError("SKILL.md frontmatter must end with ---") from exc

    data = {}  # type: Dict[str, str]
    for line in lines[1:end]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"Invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def validate_python_syntax(path):
    try:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    except SyntaxError as exc:
        return "{}:{}: {}".format(path, exc.lineno, exc.msg)
    return ""


def validate_recipe(path):
    errors = []  # type: List[str]
    text = path.read_text(encoding="utf-8")
    forbidden = [
        "../../src/",
        "source:\n  path:",
    ]
    for token in forbidden:
        if token in text:
            errors.append("{}: recipe contains forbidden local path token {!r}".format(path, token))
    if "source:" in text and "git:" not in text and "url:" not in text:
        errors.append("{}: recipe source should use a public git or url source".format(path))
    return errors


def validate_public_text(path):
    errors = []  # type: List[str]
    text = path.read_text(encoding="utf-8")
    for token in FORBIDDEN_PUBLIC_TOKENS:
        if token in text:
            errors.append(f"{path.relative_to(REPO_ROOT)} contains forbidden public token {token!r}")
    return errors


def load_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"{path}: invalid JSON: {exc}", None

    return "", data


def validate_plugin_manifest(skill_dir):
    errors = []  # type: List[str]
    skill_name = skill_dir.name
    manifest = skill_dir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        errors.append(f"{skill_name}: missing .claude-plugin/plugin.json")
        return errors

    error, data = load_json(manifest)
    if error:
        errors.append(f"{skill_name}: {error}")
        return errors
    if not isinstance(data, dict):
        errors.append(f"{skill_name}: plugin manifest must be a JSON object")
        return errors

    if data.get("name") != skill_name:
        errors.append(f"{skill_name}: plugin manifest name must match folder name")
    if not data.get("description"):
        errors.append(f"{skill_name}: plugin manifest is missing description")
    if not data.get("version"):
        errors.append(f"{skill_name}: plugin manifest is missing version")
    skills = data.get("skills")
    if skills is not None and "./" not in skills:
        errors.append(f"{skill_name}: plugin manifest skills should include ./")

    return errors


def validate_marketplace(skills):
    errors = []  # type: List[str]
    marketplace = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    if not marketplace.exists():
        errors.append("Missing .claude-plugin/marketplace.json")
        return errors

    error, data = load_json(marketplace)
    if error:
        errors.append(error)
        return errors
    if not isinstance(data, dict):
        errors.append("Marketplace manifest must be a JSON object")
        return errors

    marketplace_name = data.get("name")
    if not isinstance(marketplace_name, str) or not MARKETPLACE_NAME_RE.fullmatch(marketplace_name):
        errors.append("Marketplace name must be lowercase hyphen-case")

    skill_names = {path.name for path in skills}
    plugins = data.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        errors.append("Marketplace must define a non-empty plugins list")
        return errors

    listed_names = set()
    for index, plugin in enumerate(plugins):
        if not isinstance(plugin, dict):
            errors.append(f"Marketplace plugin #{index + 1} must be an object")
            continue
        name = plugin.get("name")
        source = plugin.get("source")
        if name not in skill_names:
            errors.append(f"Marketplace plugin #{index + 1} references unknown skill {name!r}")
        if source != f"./skills/{name}":
            errors.append(f"{name}: marketplace source must be ./skills/{name}")
        if not plugin.get("description"):
            errors.append(f"{name}: marketplace entry is missing description")
        if name in listed_names:
            errors.append(f"{name}: duplicate marketplace plugin entry")
        listed_names.add(name)

    return errors


def validate_skill(skill_dir):
    errors = []  # type: List[str]
    skill_name = skill_dir.name

    if not NAME_RE.fullmatch(skill_name):
        errors.append(f"{skill_name}: folder name must be lowercase hyphen-case")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_name}: missing SKILL.md"]

    try:
        frontmatter = parse_frontmatter(skill_md)
    except ValueError as exc:
        return [f"{skill_name}: {exc}"]

    if frontmatter.get("name") != skill_name:
        errors.append(f"{skill_name}: frontmatter name must match folder name")

    errors.extend(validate_plugin_manifest(skill_dir))

    description = frontmatter.get("description", "")
    if not description:
        errors.append(f"{skill_name}: missing description")
    if "TODO" in description or description.startswith("["):
        errors.append(f"{skill_name}: description still looks like a placeholder")

    forbidden = sorted(path for path in skill_dir.rglob("README*") if path.is_file())
    for path in forbidden:
        errors.append(f"{skill_name}: remove per-skill README file {path.relative_to(skill_dir)}")

    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if openai_yaml.exists():
        text = openai_yaml.read_text(encoding="utf-8")
        if f"${skill_name}" not in text:
            errors.append(f"{skill_name}: agents/openai.yaml default_prompt should mention ${skill_name}")

    for script in (skill_dir / "scripts").glob("*.py") if (skill_dir / "scripts").exists() else []:
        syntax_error = validate_python_syntax(script)
        if syntax_error:
            errors.append(f"{skill_name}: {script.relative_to(skill_dir)} does not compile: {syntax_error}")

    assets_root = skill_dir / "assets"
    if assets_root.exists():
        for recipe in assets_root.rglob("recipe.yaml"):
            for error in validate_recipe(recipe):
                errors.append("{}: {}".format(skill_name, error))

    return errors


def main():
    if not SKILLS_DIR.exists():
        print(f"Missing skills directory: {SKILLS_DIR}", file=sys.stderr)
        return 1

    errors = []  # type: List[str]
    skills = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    if not skills:
        errors.append("No skills found")

    for skill_dir in skills:
        errors.extend(validate_skill(skill_dir))

    errors.extend(validate_marketplace(skills))

    for script in (REPO_ROOT / "scripts").glob("*.py"):
        syntax_error = validate_python_syntax(script)
        if syntax_error:
            errors.append(f"{script.relative_to(REPO_ROOT)} does not compile: {syntax_error}")

    for path in REPO_ROOT.rglob("*"):
        if path.is_file() and ".git" not in path.parts:
            if path.suffix in {".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt"}:
                errors.extend(validate_public_text(path))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(skills)} skill(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
