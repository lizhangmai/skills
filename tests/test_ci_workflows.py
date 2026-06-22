from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_runs_static_repository_gates():
    text = CI_WORKFLOW.read_text(encoding="utf-8")

    required_commands = [
        "python -m py_compile",
        "pytest -q",
        "python scripts/validate.py",
        "python scripts/skill_harness.py run",
        "git diff --check",
    ]

    for command in required_commands:
        assert command in text


def test_ci_keeps_harness_reports_as_artifacts():
    text = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "reports/skill-harness" in text
    assert "actions/upload-artifact" in text
