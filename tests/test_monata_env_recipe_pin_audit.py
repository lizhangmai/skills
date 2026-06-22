import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "monata-env"
    / "skills"
    / "monata-env"
    / "scripts"
    / "audit_recipe_pins.py"
)
RECIPE_ROOT = (
    REPO_ROOT
    / "plugins"
    / "conda-build"
    / "skills"
    / "conda-build"
    / "assets"
    / "recipe-sets"
    / "circuit-toolchain"
    / "recipes"
)


def run_audit(*args):
    return subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--format", "json", *map(str, args)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_recipe_pin_audit_passes_for_current_circuit_toolchain():
    result = run_audit()

    assert result.returncode == 0, result.stderr + result.stdout
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert not data["errors"]
    assert data["pins_file"].endswith("circuit-tool-pins.json")

    klayout = data["packages"]["klayout"]
    assert klayout["version"] == "0.30.9"
    assert klayout["source_ref"] == "v0.30.9"
    assert klayout["source_commit"] == "6270877110ef808dd442fd2244164cec06a7b10e"
    assert klayout["planner_package_spec"] == "klayout=0.30.9"
    assert klayout["recipe_sha256"] == "cda63ae729ac6e1bba92d1003e1af12093db5bb7c45dca241337ca27dc68bedf"

    xschem = data["packages"]["xschem"]
    assert xschem["version"] == "3.4.7"
    assert xschem["source_ref"] == "3.4.7"
    assert xschem["source_commit"] == "92dd8fe5f4d5c1057489710d8a22f18fdc9d7ed0"
    assert xschem["planner_package_spec"] == "xschem=3.4.7"
    assert xschem["recipe_sha256"] == "2d292390a9144082a79b862c2ef39bc67164868f466ad5dfbc9367f498fede16"

    for package in data["packages"].values():
        assert package["checks"] == [
            "planner-source-ref",
            "planner-package-spec",
            "recipe-version",
            "recipe-source-commit",
            "recipe-sha256",
        ]


def test_recipe_pin_audit_reports_recipe_version_drift(tmp_path):
    recipe_root = tmp_path / "recipes"
    shutil.copytree(RECIPE_ROOT, recipe_root)
    klayout_recipe = recipe_root / "klayout" / "recipe.yaml"
    klayout_recipe.write_text(
        klayout_recipe.read_text(encoding="utf-8").replace('version: "0.30.9"', 'version: "0.30.8"', 1),
        encoding="utf-8",
    )

    result = run_audit("--recipe-root", recipe_root)

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert {
        (error["package"], error["check"])
        for error in data["errors"]
    } == {("klayout", "recipe-version")}
