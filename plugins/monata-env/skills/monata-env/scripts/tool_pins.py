"""Load maintained circuit-tool version pins for monata-env."""

import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DEFAULT_PINS_FILE = SKILL_ROOT / "references" / "circuit-tool-pins.json"
BASE_PIXI_PACKAGE_SPECS = {
    "ngspice": "ngspice=46.0",
    "openvaf-r": "openvaf-r",
}
BASE_EXPOSED_COMMANDS = {
    "ngspice": "ngspice",
    "openvaf-r": "openvaf-r",
}


def load_tool_pins(path=None):
    pins_file = Path(path).expanduser().resolve() if path else DEFAULT_PINS_FILE
    return json.loads(pins_file.read_text(encoding="utf-8"))


def expected_source_refs(pins):
    return {
        package: data["source_ref"]
        for package, data in pins.get("packages", {}).items()
        if data.get("source_ref")
    }


def pixi_package_specs(pins):
    specs = dict(BASE_PIXI_PACKAGE_SPECS)
    specs.update(
        {
            package: data["planner_package_spec"]
            for package, data in pins.get("packages", {}).items()
            if data.get("planner_package_spec")
        }
    )
    return specs


def exposed_commands(pins):
    commands = dict(BASE_EXPOSED_COMMANDS)
    commands.update({package: package for package in pins.get("packages", {})})
    return commands
