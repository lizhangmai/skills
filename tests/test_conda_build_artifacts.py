import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "conda-build"
    / "skills"
    / "conda-build"
    / "scripts"
    / "test_circuit_artifacts.py"
)
SKILL_MD = REPO_ROOT / "plugins" / "conda-build" / "skills" / "conda-build" / "SKILL.md"
REFERENCE_MD = (
    REPO_ROOT
    / "plugins"
    / "conda-build"
    / "skills"
    / "conda-build"
    / "references"
    / "circuit-toolchain-recipes.md"
)


def load_module():
    spec = importlib.util.spec_from_file_location("test_circuit_artifacts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_artifact_smoke_profile_is_monata_env_baseline(tmp_path):
    module = load_module()
    manifest = tmp_path / "pixi.toml"

    module.write_manifest(manifest, tmp_path / "channel", [], profile="monata-env-baseline")

    text = manifest.read_text(encoding="utf-8")
    assert '[feature."monata-env-baseline".dependencies]' in text
    assert 'ngspice = "46.0.*"' in text
    assert 'openvaf-r = "0.4.0.*"' in text
    assert 'klayout = "0.30.9.*"' in text
    assert 'xschem = "3.4.7.*"' in text
    assert 'adms = "2.3.7.*"' not in text
    assert 'xyce = "7.11.0.*"' not in text
    assert 'monata = "0.1.0.*"' not in text
    assert '"monata-env-baseline" = ["monata-env-baseline"]' in text


def test_full_artifact_smoke_profile_keeps_complete_toolchain(tmp_path):
    module = load_module()
    manifest = tmp_path / "pixi.toml"

    module.write_manifest(manifest, tmp_path / "channel", [], profile="full-toolchain")

    text = manifest.read_text(encoding="utf-8")
    assert '[feature."full-toolchain".dependencies]' in text
    assert 'adms = "2.3.7.*"' in text
    assert 'vacask = "0.1.0.*"' in text
    assert 'xyce = "7.11.0.*"' in text
    assert 'monata = "0.1.0.*"' in text
    assert 'inspice = "1.7.0.3.*"' in text
    assert '"full-toolchain" = ["full-toolchain"]' in text
    assert 'trilinos17 = ["trilinos17"]' in text


def test_pixi_smoke_uses_selected_profile_without_trilinos_for_baseline(tmp_path, monkeypatch):
    module = load_module()
    output_dir = tmp_path / "channel"
    output_dir.mkdir()
    work_dir = tmp_path / "work"
    commands = []

    def fake_run(command, cwd=None, timeout=None):
        commands.append([str(part) for part in command])

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda command: "/tmp/fake-pixi" if command == "pixi" else None)
    args = module.parse_args(
        [
            "--output-dir",
            str(output_dir),
            "--work-dir",
            str(work_dir),
            "--profile",
            "monata-env-baseline",
        ]
    )

    module.run_pixi_smoke(args)

    assert len(commands) == 1
    assert "-e" in commands[0]
    assert commands[0][commands[0].index("-e") + 1] == "monata-env-baseline"
    assert "--inside-profile" in commands[0]
    assert commands[0][commands[0].index("--inside-profile") + 1] == "monata-env-baseline"


def test_conda_index_guidance_uses_conda_plugin_command_not_fake_executable():
    text = SKILL_MD.read_text(encoding="utf-8")

    assert "conda index <channel-dir>" in text
    assert "CONDA_NO_PLUGINS" in text
    assert "conda-index=conda-index" in text
    assert "Do not expose" in text


def test_circuit_artifact_docs_recommend_monata_env_baseline_profile():
    text = REFERENCE_MD.read_text(encoding="utf-8")

    assert "--profile monata-env-baseline" in text
    assert "--profile full-toolchain" in text
    assert "monata-env-baseline" in text
    assert "ngspice`, `openvaf-r`, `klayout`, and `xschem" in text
