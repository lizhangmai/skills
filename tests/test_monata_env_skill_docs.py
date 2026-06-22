from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env"
SKILL = SKILL_DIR / "SKILL.md"


def test_monata_env_skill_keeps_main_doc_focused_with_references():
    text = SKILL.read_text(encoding="utf-8")
    lines = text.splitlines()

    assert len(lines) <= 430
    for reference in (
        "references/setup-workflow.md",
        "references/isolated-testing.md",
        "references/error-codes.json",
    ):
        assert (SKILL_DIR / reference).exists()
        assert reference in text


def test_monata_env_skill_retains_core_guardrails_after_split():
    text = SKILL.read_text(encoding="utf-8")

    required_phrases = [
        "Do not install Monata.",
        "Do not install the `monata` Python package.",
        "Do not bootstrap Monata techlibs.",
        "Start with `scripts/plan_monata_env.py`",
        "Prefer `scripts/execute_monata_env_runbook.py`",
        "If the executor returns `next_actions`, do not blindly retry.",
        "Create or update a pixi global environment named `monata-env`",
    ]

    for phrase in required_phrases:
        assert phrase in text
