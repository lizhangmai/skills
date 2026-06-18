#!/usr/bin/env python
"""Validate the multi-plugin skills repository structure."""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = REPO_ROOT / "plugins"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKETPLACE_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_PUBLIC_TOKENS = [
    "/" + "workspace" + "/",
    "/" + "share" + "/personal" + "/",
    "lizhangmai" + "-skills",
    "github.com/lizhangmai/" + "lizhangmai" + "-skills",
]
LOCAL_STATE_DIRS = {
    ".git",
    ".mypy_cache",
    ".omx",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "reports",
}
PUBLIC_TEXT_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt"}


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


def iter_public_text_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in LOCAL_STATE_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        if path.suffix in PUBLIC_TEXT_SUFFIXES:
            yield path


def load_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"{path}: invalid JSON: {exc}", None
    except OSError as exc:
        return f"{path}: unable to read JSON: {exc}", None

    return "", data


def plugin_dirs():
    if not PLUGINS_DIR.exists():
        return []
    return sorted(path for path in PLUGINS_DIR.iterdir() if path.is_dir())


def skill_dir_for_plugin(plugin_dir):
    return plugin_dir / "skills" / plugin_dir.name


def validate_claude_plugin_manifest(plugin_dir):
    errors = []  # type: List[str]
    plugin_name = plugin_dir.name
    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        errors.append(f"{plugin_name}: missing .claude-plugin/plugin.json")
        return errors

    error, data = load_json(manifest)
    if error:
        errors.append(f"{plugin_name}: {error}")
        return errors
    if not isinstance(data, dict):
        errors.append(f"{plugin_name}: Claude plugin manifest must be a JSON object")
        return errors

    if data.get("name") != plugin_name:
        errors.append(f"{plugin_name}: Claude plugin manifest name must match folder name")
    if not data.get("description"):
        errors.append(f"{plugin_name}: Claude plugin manifest is missing description")
    if not data.get("version"):
        errors.append(f"{plugin_name}: Claude plugin manifest is missing version")
    if data.get("skills") != [f"./skills/{plugin_name}"]:
        errors.append(f"{plugin_name}: Claude plugin skills must be ./skills/{plugin_name}")

    return errors


def validate_codex_plugin_manifest(plugin_dir):
    errors = []  # type: List[str]
    plugin_name = plugin_dir.name
    manifest = plugin_dir / ".codex-plugin" / "plugin.json"
    if not manifest.exists():
        errors.append(f"{plugin_name}: missing .codex-plugin/plugin.json")
        return errors

    error, data = load_json(manifest)
    if error:
        errors.append(f"{plugin_name}: {error}")
        return errors
    if not isinstance(data, dict):
        errors.append(f"{plugin_name}: Codex plugin manifest must be a JSON object")
        return errors

    if data.get("name") != plugin_name:
        errors.append(f"{plugin_name}: Codex plugin manifest name must match folder name")
    if data.get("skills") != "./skills/":
        errors.append(f"{plugin_name}: Codex plugin skills must be ./skills/")
    if not isinstance(data.get("interface"), dict):
        errors.append(f"{plugin_name}: Codex plugin manifest is missing interface metadata")

    return errors


def validate_claude_marketplace(plugins):
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
        errors.append("Claude marketplace manifest must be a JSON object")
        return errors

    plugin_names = {path.name for path in plugins}
    entries = data.get("plugins")
    if not isinstance(entries, list) or not entries:
        errors.append("Claude marketplace must define a non-empty plugins list")
        return errors

    listed_names = set()
    for index, plugin in enumerate(entries):
        if not isinstance(plugin, dict):
            errors.append(f"Claude marketplace plugin #{index + 1} must be an object")
            continue
        name = plugin.get("name")
        source = plugin.get("source")
        if name not in plugin_names:
            errors.append(f"Claude marketplace plugin #{index + 1} references unknown plugin {name!r}")
        if source != f"./plugins/{name}":
            errors.append(f"{name}: Claude marketplace source must be ./plugins/{name}")
        if not plugin.get("description"):
            errors.append(f"{name}: Claude marketplace entry is missing description")
        if name in listed_names:
            errors.append(f"{name}: duplicate Claude marketplace plugin entry")
        listed_names.add(name)

    return errors


def validate_codex_marketplace(plugins):
    errors = []  # type: List[str]
    marketplace = REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
    if not marketplace.exists():
        errors.append("Missing .agents/plugins/marketplace.json")
        return errors

    error, data = load_json(marketplace)
    if error:
        errors.append(error)
        return errors
    if not isinstance(data, dict):
        errors.append("Codex marketplace manifest must be a JSON object")
        return errors

    marketplace_name = data.get("name")
    if not isinstance(marketplace_name, str) or not MARKETPLACE_NAME_RE.fullmatch(marketplace_name):
        errors.append("Codex marketplace name must be lowercase hyphen-case")

    plugin_names = {path.name for path in plugins}
    entries = data.get("plugins")
    if not isinstance(entries, list) or not entries:
        errors.append("Codex marketplace must define a non-empty plugins list")
        return errors

    listed_names = set()
    for index, plugin in enumerate(entries):
        if not isinstance(plugin, dict):
            errors.append(f"Codex marketplace plugin #{index + 1} must be an object")
            continue
        name = plugin.get("name")
        source = plugin.get("source")
        if name not in plugin_names:
            errors.append(f"Codex marketplace plugin #{index + 1} references unknown plugin {name!r}")
        expected_source = {"source": "local", "path": f"./plugins/{name}"}
        if source != expected_source:
            errors.append(f"{name}: Codex marketplace source must be {expected_source!r}")
        policy = plugin.get("policy")
        if not isinstance(policy, dict):
            errors.append(f"{name}: Codex marketplace entry is missing policy")
        else:
            if policy.get("installation") != "AVAILABLE":
                errors.append(f"{name}: Codex marketplace policy.installation must be AVAILABLE")
            if policy.get("authentication") != "ON_INSTALL":
                errors.append(f"{name}: Codex marketplace policy.authentication must be ON_INSTALL")
        if not plugin.get("category"):
            errors.append(f"{name}: Codex marketplace entry is missing category")
        if name in listed_names:
            errors.append(f"{name}: duplicate Codex marketplace plugin entry")
        listed_names.add(name)

    return errors


def validate_skill(plugin_dir):
    errors = []  # type: List[str]
    skill_name = plugin_dir.name
    skill_dir = skill_dir_for_plugin(plugin_dir)

    if not NAME_RE.fullmatch(skill_name):
        errors.append(f"{skill_name}: folder name must be lowercase hyphen-case")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_name}: missing {skill_md.relative_to(REPO_ROOT)}"]

    try:
        frontmatter = parse_frontmatter(skill_md)
    except ValueError as exc:
        return [f"{skill_name}: {exc}"]

    if frontmatter.get("name") != skill_name:
        errors.append(f"{skill_name}: frontmatter name must match folder name")

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
    if not PLUGINS_DIR.exists():
        print(f"Missing plugins directory: {PLUGINS_DIR}", file=sys.stderr)
        return 1

    errors = []  # type: List[str]
    plugins = plugin_dirs()
    if not plugins:
        errors.append("No plugins found")

    for plugin_dir in plugins:
        errors.extend(validate_claude_plugin_manifest(plugin_dir))
        errors.extend(validate_codex_plugin_manifest(plugin_dir))
        errors.extend(validate_skill(plugin_dir))

    errors.extend(validate_claude_marketplace(plugins))
    errors.extend(validate_codex_marketplace(plugins))

    for script in (REPO_ROOT / "scripts").glob("*.py"):
        syntax_error = validate_python_syntax(script)
        if syntax_error:
            errors.append(f"{script.relative_to(REPO_ROOT)} does not compile: {syntax_error}")

    for path in iter_public_text_files():
        errors.extend(validate_public_text(path))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(plugins)} plugin(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
