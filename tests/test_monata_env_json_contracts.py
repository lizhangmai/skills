import json
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "schemas"
ERROR_CODES = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "references" / "error-codes.json"
PLAN_SCRIPT = REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "plan_monata_env.py"
EXECUTE_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "execute_monata_env_runbook.py"
)
VALIDATE_SCRIPT = (
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "validate_json_contract.py"
)
STRUCTURED_ERROR_SCRIPTS = [
    REPO_ROOT / "plugins" / "conda-build" / "skills" / "conda-build" / "scripts" / "rattler_channel.py",
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "execute_monata_env_runbook.py",
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "skill_container.py",
    REPO_ROOT / "plugins" / "monata-env" / "skills" / "monata-env" / "scripts" / "test_monata_env_upstream.py",
]


def run(command, **kwargs):
    return subprocess.run(
        [str(part) for part in command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        **kwargs,
    )


def write_monata_workspace(path: Path) -> None:
    path.mkdir(parents=True)
    (path / "pyproject.toml").write_text('[project]\nname = "monata"\n', encoding="utf-8")
    (path / "README.md").write_text("Monata workspace using ngspice, KLayout, and Xschem.\n", encoding="utf-8")


def test_core_json_contract_schemas_are_versioned():
    expected = {
        "audit-report.schema.json",
        "error.schema.json",
        "manifest.schema.json",
        "next-action.schema.json",
        "plan.schema.json",
        "runbook-summary.schema.json",
        "tool-smoke.schema.json",
        "upstream-tests.schema.json",
    }

    found = {path.name for path in SCHEMA_DIR.glob("*.schema.json")}

    assert expected <= found
    for name in expected:
        schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"]
        assert schema["type"] == "object"


def test_contract_validator_accepts_generated_plan_manifest_and_runbook_summary(tmp_path):
    workspace = tmp_path / "workspace"
    channel = tmp_path / "channel"
    session = tmp_path / "session"
    plan_path = tmp_path / "plan.json"
    write_monata_workspace(workspace)

    plan_result = run(
        [
            sys.executable,
            PLAN_SCRIPT,
            "--root",
            workspace,
            "--output-dir",
            channel,
            "--session-dir",
            session,
            "--write-manifest",
            "--format",
            "json",
        ]
    )

    assert plan_result.returncode == 0, plan_result.stdout
    plan_path.write_text(plan_result.stdout, encoding="utf-8")
    manifest_path = session / "monata-env-install-manifest.json"
    assert manifest_path.exists()

    runbook_result = run(
        [
            sys.executable,
            EXECUTE_SCRIPT,
            "--plan",
            plan_path,
            "--dry-run",
            "--allow-confirmation-required",
            "--include-optional",
            "--format",
            "json",
        ]
    )
    assert runbook_result.returncode == 0, runbook_result.stdout
    runbook_path = tmp_path / "runbook-summary.json"
    runbook_path.write_text(runbook_result.stdout, encoding="utf-8")

    for kind, path in (
        ("plan", plan_path),
        ("manifest", manifest_path),
        ("runbook-summary", runbook_path),
    ):
        result = run([sys.executable, VALIDATE_SCRIPT, "--kind", kind, "--file", path])
        assert result.returncode == 0, result.stdout


def test_structured_error_codes_are_registered():
    registry = json.loads(ERROR_CODES.read_text(encoding="utf-8"))
    codes = registry["codes"]
    expected = {
        "conda-build-helper-missing",
        "helper-missing",
        "local-source-missing-for-ref",
        "local-source-ref-mismatch",
        "local-source-target-ref-missing",
        "missing-required-commands",
        "network-download-failed",
        "registry-download-failed",
        "source-download-failed",
        "source-missing",
        "source-test-missing",
        "tclsh-missing",
        "tool-missing",
    }

    assert expected <= set(codes)
    for code in expected:
        entry = codes[code]
        assert entry["description"]
        assert entry["producer"]
        assert entry["recovery"]

    emitted = set()
    patterns = [
        re.compile(r"error_code in \{([^}]+)\}"),
        re.compile(r"emit_structured_error\(\s*[\"']([^\"']+)[\"']"),
        re.compile(r'"error": \{"code": ["\']([^"\']+)["\']\}'),
        re.compile(r"failure\([\"']([^\"']+)[\"']"),
    ]
    for path in STRUCTURED_ERROR_SCRIPTS:
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            for match in pattern.finditer(text):
                if pattern.pattern.startswith("error_code"):
                    emitted.update(re.findall(r"[\"']([a-z][a-z0-9]+(?:-[a-z0-9]+)+)[\"']", match.group(1)))
                else:
                    emitted.add(match.group(1))

    assert emitted <= set(codes)
