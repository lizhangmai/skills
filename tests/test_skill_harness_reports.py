import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS = REPO_ROOT / "scripts" / "skill_harness.py"
CASE_NAME = "conda-build-requires-output-dir"


def run_harness(reports_dir, *extra_args):
    return subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "run",
            CASE_NAME,
            "--reports-dir",
            str(reports_dir),
            *extra_args,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_skill_harness_cleans_stale_json_reports_before_run(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    stale_report = reports_dir / "removed-case.json"
    non_json_note = reports_dir / "notes.md"
    stale_report.write_text("{}", encoding="utf-8")
    non_json_note.write_text("keep me\n", encoding="utf-8")

    result = run_harness(reports_dir)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not stale_report.exists()
    assert non_json_note.read_text(encoding="utf-8") == "keep me\n"
    assert (reports_dir / f"{CASE_NAME}.json").exists()


def test_skill_harness_can_keep_existing_reports_when_requested(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    stale_report = reports_dir / "kept-case.json"
    stale_report.write_text("{}", encoding="utf-8")

    result = run_harness(reports_dir, "--keep-existing-reports")

    assert result.returncode == 0, result.stdout + result.stderr
    assert stale_report.exists()
    assert (reports_dir / f"{CASE_NAME}.json").exists()
