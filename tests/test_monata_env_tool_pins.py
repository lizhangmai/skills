import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_SCRIPT = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "plan_monata_env.py"
PINS_FILE = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "references" / "circuit-tool-pins.json"


def run(command):
    return subprocess.run(
        [str(part) for part in command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def write_monata_workspace(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "pyproject.toml").write_text('[project]\nname = "monata"\n', encoding="utf-8")


def git_repo_with_tagged_parent(path: Path, tag: str) -> None:
    path.mkdir(parents=True)
    run(["git", "init", path])
    (path / "source.txt").write_text("tagged\n", encoding="utf-8")
    run(["git", "-C", path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "add", "source.txt"])
    run(
        [
            "git",
            "-C",
            path,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "tagged",
        ]
    )
    run(["git", "-C", path, "tag", tag])


def test_plan_reads_pinned_tool_refs_and_specs_from_json(tmp_path):
    workspace = tmp_path / "workspace"
    output_dir = tmp_path / "channel"
    pins_file = tmp_path / "circuit-tool-pins.json"
    klayout_source = tmp_path / "klayout"
    write_monata_workspace(workspace)
    git_repo_with_tagged_parent(klayout_source, "v9.9.9")

    pins = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    pins["packages"]["klayout"]["version"] = "9.9.9"
    pins["packages"]["klayout"]["source_ref"] = "v9.9.9"
    pins["packages"]["klayout"]["planner_package_spec"] = "klayout=9.9.9"
    pins_file.write_text(json.dumps(pins, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            output_dir,
            "--tool-pins-file",
            pins_file,
            "--local-source",
            f"klayout={klayout_source}",
            "--format",
            "json",
        ]
    )

    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["local_sources"]["klayout"]["target_ref"] == "v9.9.9"
    assert data["local_sources"]["klayout"]["status"] == "ok"
    assert "klayout=9.9.9" in data["commands"]["install"]
    assert "--local-source-ref klayout=v9.9.9" in " ".join(data["commands"]["build"])
