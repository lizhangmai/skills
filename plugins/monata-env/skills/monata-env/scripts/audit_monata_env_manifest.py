#!/usr/bin/env python
"""Audit a monata-env setup manifest against the skill's hard requirements."""

import argparse
import json
import shutil
import shlex
import subprocess
from pathlib import Path


EXPECTED_TOOLS = ["ngspice", "openvaf-r", "klayout", "xschem"]
FORBIDDEN_COMMAND_SNIPPETS = [
    "pixi init",
    "pixi add",
    "pixi run python",
    "bootstrap_monata_techlibs.py",
    "TechlibRegistry",
]
FORBIDDEN_PACKAGES = ["monata"]


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Manifest is not valid JSON: {path}: {exc}") from exc


def package_name(value):
    text = str(value)
    for marker in ("=", "<", ">", "!"):
        if marker in text:
            text = text.split(marker, 1)[0]
    return text.strip()


def command_strings(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings = []
        for item in value.values():
            strings.extend(command_strings(item))
        return strings
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return [shlex.join(str(item) for item in value)]
        strings = []
        for item in value:
            strings.extend(command_strings(item))
        return strings
    return [str(value)]


def command_tokens(value):
    tokens = []
    for text in command_strings(value):
        try:
            tokens.extend(shlex.split(text))
        except ValueError:
            tokens.extend(text.split())
    return tokens


def all_command_strings(manifest):
    plan = manifest.get("plan", {})
    strings = []
    strings.extend(command_strings(plan.get("commands")))
    strings.extend(command_strings([step.get("command", []) for step in plan.get("runbook", [])]))
    for command in manifest.get("execution", {}).get("commands_run", []):
        strings.extend(command_strings(command.get("command")))
    return strings


def all_command_tokens(manifest):
    plan = manifest.get("plan", {})
    tokens = []
    tokens.extend(command_tokens(plan.get("commands")))
    tokens.extend(command_tokens([step.get("command", []) for step in plan.get("runbook", [])]))
    for command in manifest.get("execution", {}).get("commands_run", []):
        tokens.extend(command_tokens(command.get("command")))
    return tokens


def monata_package_token(token):
    name = package_name(token)
    return name == "monata"


def requirement(req_id, title, ok, reason="", **extra):
    item = {
        "id": req_id,
        "title": title,
        "ok": bool(ok),
    }
    if reason:
        item["reason"] = reason
    item.update(extra)
    return item


def expected_tool_plan(manifest):
    plan = manifest.get("plan", {})
    packages = [package_name(item) for item in plan.get("packages", [])]
    missing = [tool for tool in EXPECTED_TOOLS if tool not in packages]
    return requirement(
        "expected-tool-plan",
        "Plan includes the Monata circuit-tool baseline",
        not missing,
        "ok" if not missing else "missing-tools",
        expected=EXPECTED_TOOLS,
        planned=packages,
        missing=missing,
    )


def forbidden_scope(manifest):
    plan = manifest.get("plan", {})
    packages = [package_name(item) for item in plan.get("packages", [])]
    problems = [package for package in packages if package == "monata"]
    strings = all_command_strings(manifest)
    for snippet in FORBIDDEN_COMMAND_SNIPPETS:
        if any(snippet in text for text in strings):
            problems.append(snippet)
    for token in all_command_tokens(manifest):
        if monata_package_token(token):
            problems.append("monata")
    problems = sorted(set(problems))
    return requirement(
        "no-monata-or-techlibs",
        "No Monata package or techlib bootstrap is planned or recorded",
        not problems,
        "ok" if not problems else "forbidden-scope",
        problems=problems,
    )


def install_succeeded(manifest):
    records = [
        command
        for command in manifest.get("execution", {}).get("commands_run", [])
        if command.get("kind") == "install"
    ]
    if not records:
        return requirement(
            "install-command-succeeded",
            "pixi global install command completed",
            False,
            "install-not-recorded",
        )
    ok_records = [record for record in records if record.get("returncode") == 0]
    return requirement(
        "install-command-succeeded",
        "pixi global install command completed",
        bool(ok_records),
        "ok" if ok_records else "install-failed",
        attempts=len(records),
        last_returncode=records[-1].get("returncode"),
    )


def smoke_passed(manifest):
    smoke = manifest.get("verification", {}).get("smoke")
    if not isinstance(smoke, dict):
        return requirement(
            "installed-tool-smoke",
            "Installed tool smoke tests passed",
            False,
            "smoke-not-recorded",
            expected=EXPECTED_TOOLS,
        )
    tools = smoke.get("tools", {})
    missing = [tool for tool in EXPECTED_TOOLS if tool not in tools]
    failed = [
        tool
        for tool in EXPECTED_TOOLS
        if isinstance(tools.get(tool), dict) and not tools[tool].get("ok")
    ]
    ok = smoke.get("ok") is True and not missing and not failed
    return requirement(
        "installed-tool-smoke",
        "Installed tool smoke tests passed",
        ok,
        "ok" if ok else smoke.get("reason", "smoke-failed"),
        expected=EXPECTED_TOOLS,
        missing=missing,
        failed=failed,
    )


def upstream_recommendation(manifest):
    plan = manifest.get("plan", {})
    profile = plan.get("test_profiles", {}).get("upstream_installed", {})
    recommended = bool(profile.get("recommended"))
    payload = manifest.get("verification", {}).get("upstream_installed")
    if not recommended and payload is None:
        return {
            "id": "upstream-installed-tests",
            "ok": True,
            "recommended": False,
            "status": "not-requested",
        }
    if payload is None:
        return {
            "id": "upstream-installed-tests",
            "ok": True,
            "recommended": recommended,
            "status": "not-run",
        }
    ok = isinstance(payload, dict) and payload.get("ok") is True
    return {
        "id": "upstream-installed-tests",
        "ok": ok,
        "recommended": recommended,
        "status": "passed" if ok else "failed",
        "reason": payload.get("reason", "upstream-failed") if isinstance(payload, dict) and not ok else "ok",
    }


def normalize_items(items, key):
    values = []
    seen = set()
    for item in items or []:
        if isinstance(item, dict):
            value = item.get(key) or item.get("name")
        else:
            value = item
        if value and str(value) not in seen:
            values.append(str(value))
            seen.add(str(value))
    return values


def pixi_global_env(env_name):
    pixi = shutil.which("pixi")
    if pixi is None:
        return None, {
            "returncode": None,
            "reason": "pixi-missing",
            "output": "",
        }
    result = subprocess.run(
        [pixi, "global", "list", "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        return None, {
            "returncode": result.returncode,
            "reason": "pixi-global-list-failed",
            "output": result.stdout[-4000:],
        }
    try:
        environments = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return None, {
            "returncode": result.returncode,
            "reason": "pixi-global-list-invalid-json",
            "output": result.stdout[-4000:],
            "error": str(exc),
        }
    if isinstance(environments, dict):
        environments = environments.get("environments") or environments.get("envs") or []
    for item in environments:
        if isinstance(item, dict) and item.get("name") == env_name:
            return item, {
                "returncode": result.returncode,
                "reason": "ok",
                "output": "",
            }
    return None, {
        "returncode": result.returncode,
        "reason": "pixi-env-missing",
        "output": result.stdout[-4000:],
    }


def live_state_requirement(manifest):
    plan = manifest.get("plan", {})
    env_name = plan.get("env_name") or "monata-env"
    expected_tools = list(EXPECTED_TOOLS)
    command_paths = {tool: shutil.which(tool) or "" for tool in expected_tools}
    missing_commands = [tool for tool, path in command_paths.items() if not path]
    env, pixi_status = pixi_global_env(env_name)
    packages = []
    exposed = []
    if env:
        packages = normalize_items(env.get("dependencies"), "name")
        exposed = normalize_items(env.get("exposed"), "exposed_name")
    missing_packages = [tool for tool in expected_tools if tool not in packages]
    missing_exposures = [tool for tool in expected_tools if tool not in exposed]
    forbidden_packages = [package for package in FORBIDDEN_PACKAGES if package in packages]
    ok = (
        pixi_status["reason"] == "ok"
        and not missing_commands
        and not missing_packages
        and not missing_exposures
        and not forbidden_packages
    )
    return requirement(
        "live-monata-env",
        "Current pixi global monata-env state matches the manifest requirements",
        ok,
        "ok" if ok else "live-state-mismatch",
        env_name=env_name,
        pixi_status=pixi_status,
        packages=packages,
        exposed=exposed,
        command_paths={tool: path for tool, path in command_paths.items() if path},
        missing_commands=missing_commands,
        missing_packages=missing_packages,
        missing_exposures=missing_exposures,
        forbidden_packages=forbidden_packages,
    )


def command_evidence(manifest):
    records = manifest.get("execution", {}).get("commands_run", [])
    by_kind = {}
    for record in records:
        kind = record.get("kind", "")
        if not kind:
            continue
        item = {
            "command": record.get("command", ""),
            "returncode": record.get("returncode"),
            "ok": record.get("returncode") == 0,
        }
        if record.get("stdout_file"):
            item["stdout_file"] = record["stdout_file"]
        if record.get("stderr_file"):
            item["stderr_file"] = record["stderr_file"]
        by_kind[kind] = item
    return {
        "total": len(records),
        "by_kind": by_kind,
    }


def artifact_evidence(manifest):
    artifacts = manifest.get("execution", {}).get("artifacts", [])
    present = []
    seen = set()
    for artifact in artifacts:
        package = artifact.get("package")
        if package and package not in seen:
            present.append(package)
            seen.add(package)
    missing = [tool for tool in EXPECTED_TOOLS if tool not in seen]
    return {
        "expected_packages": EXPECTED_TOOLS,
        "present_packages": present,
        "missing_packages": missing,
        "files": artifacts,
    }


def package_artifacts_recorded(manifest):
    artifacts = artifact_evidence(manifest)
    missing = artifacts["missing_packages"]
    return requirement(
        "package-artifacts-recorded",
        "Package artifacts are recorded for every required tool",
        not missing,
        "ok" if not missing else "missing-artifacts",
        expected=EXPECTED_TOOLS,
        present=artifacts["present_packages"],
        missing=missing,
    )


def verification_status(manifest, recommendation, live):
    verification = manifest.get("verification", {})
    smoke = verification.get("smoke")
    audit_payload = verification.get("audit")
    return {
        "smoke": "passed" if isinstance(smoke, dict) and smoke.get("ok") is True else "failed" if smoke else "not-run",
        "upstream_installed": recommendation["status"],
        "audit": "passed" if isinstance(audit_payload, dict) and audit_payload.get("ok") is True else "failed" if audit_payload else "not-run",
        "live_state": "matched" if live and live["ok"] else "mismatch" if live else "not-checked",
    }


def evidence(manifest, recommendation, live):
    return {
        "commands": command_evidence(manifest),
        "artifacts": artifact_evidence(manifest),
        "verification": verification_status(manifest, recommendation, live),
    }


def next_actions(requirements, recommendation, manifest_path=None):
    actions = []
    by_id = {item["id"]: item for item in requirements}
    live = by_id.get("live-monata-env")
    if live and not live["ok"]:
        actions.append(
            {
                "id": "repair-live-monata-env",
                "title": "Repair the current pixi global monata-env state",
                "requires_user_input": True,
                "command": "pixi global list --json",
                "prompt": "The current pixi global monata-env state does not match the manifest. Inspect the live package/exposure mismatch, then rerun the install and smoke/audit runbook steps in an isolated or approved environment.",
            }
        )
    if not by_id["no-monata-or-techlibs"]["ok"]:
        actions.append(
            {
                "id": "remove-monata-techlib-bootstrap",
                "title": "Re-plan without Monata or techlib bootstrap",
                "requires_user_input": False,
                "prompt": "The manifest includes Monata package installation or techlib bootstrap commands. Re-run the planner and keep only reusable circuit tools in monata-env.",
            }
        )
    if not by_id["expected-tool-plan"]["ok"]:
        actions.append(
            {
                "id": "replan-required-circuit-tools",
                "title": "Re-plan the required circuit tools",
                "requires_user_input": False,
                "prompt": "The plan does not include the full ngspice/openvaf-r/KLayout/Xschem baseline. Re-run the planner before installing.",
            }
        )
    if not by_id["install-command-succeeded"]["ok"]:
        actions.append(
            {
                "id": "run-monata-env-install",
                "title": "Run or retry pixi global install",
                "requires_user_input": True,
                "prompt": "The pixi global install step has not succeeded. Confirm the global environment update, then run the install step from the runbook.",
            }
        )
    if not by_id["installed-tool-smoke"]["ok"]:
        actions.append(
            {
                "id": "inspect-installed-tools",
                "title": "Inspect exposed monata-env tool commands",
                "requires_user_input": False,
                "command": "python scripts/smoke_monata_env_tools.py --format json",
                "prompt": "The installed-tool smoke verification is missing or failed. Inspect which command is missing or failing before finalizing.",
            }
        )
    artifact_requirement = by_id.get("package-artifacts-recorded")
    if artifact_requirement and not artifact_requirement["ok"]:
        command = "python scripts/execute_monata_env_runbook.py --manifest <manifest> --step check_channel --format json"
        if manifest_path:
            command = (
                "python scripts/execute_monata_env_runbook.py "
                f"--manifest {shlex.quote(str(manifest_path))} --step check_channel --format json"
            )
        actions.append(
            {
                "id": "record-package-artifacts",
                "title": "Record local channel package artifacts",
                "requires_user_input": False,
                "command": command,
                "evidence": {
                    "missing_packages": artifact_requirement.get("missing", []),
                    "present_packages": artifact_requirement.get("present", []),
                    "manifest": str(manifest_path) if manifest_path else "",
                },
                "decision": {
                    "id": "artifact_evidence_repair",
                    "prompt": "How should missing package artifact evidence be repaired?",
                    "default": "record_existing_channel",
                    "options": [
                        {
                            "id": "record_existing_channel",
                            "label": "Record existing channel",
                            "requires_user_input": False,
                            "effect": "Run the check_channel step so record_after captures artifacts already present in the local channel.",
                        },
                        {
                            "id": "build_missing_packages",
                            "label": "Build missing packages",
                            "requires_user_input": True,
                            "effect": "Run the build step when artifacts are not present in the local channel.",
                        },
                    ],
                },
                "prompt": "The manifest is missing package artifact evidence. Run the check_channel or build runbook step so record_after captures ngspice/openvaf-r/KLayout/Xschem artifacts from the local channel.",
            }
        )
    if recommendation["status"] == "not-run" and recommendation.get("recommended"):
        actions.append(
            {
                "id": "run-upstream-installed-tests",
                "title": "Run upstream-installed checks",
                "requires_user_input": True,
                "prompt": "Local KLayout/Xschem sources are available, so run the upstream-installed test profile when the user accepts the extra runtime.",
            }
        )
    return actions


def audit(manifest_path, check_live=False, require_artifacts=False):
    manifest = load_json(manifest_path)
    requirements = [
        expected_tool_plan(manifest),
        forbidden_scope(manifest),
        install_succeeded(manifest),
        smoke_passed(manifest),
    ]
    if require_artifacts:
        requirements.append(package_artifacts_recorded(manifest))
    if check_live:
        requirements.append(live_state_requirement(manifest))
    recommendation = upstream_recommendation(manifest)
    ok = all(item["ok"] for item in requirements)
    actions = next_actions(requirements, recommendation, manifest_path=manifest_path)
    status = "ready" if ok else "blocked"
    live = next((item for item in requirements if item["id"] == "live-monata-env"), None)
    verification = verification_status(manifest, recommendation, live)
    return {
        "ok": ok,
        "status": status,
        "manifest": str(manifest_path),
        "summary": {
            "env_name": manifest.get("plan", {}).get("env_name", ""),
            "required_tools": EXPECTED_TOOLS,
            "install_ok": requirements[2]["ok"],
            "smoke_ok": requirements[3]["ok"],
            "live_state": verification["live_state"],
            "upstream_installed": recommendation["status"],
        },
        "evidence": evidence(manifest, recommendation, live),
        "requirements": requirements,
        "recommendations": [recommendation],
        "next_actions": actions,
    }


def print_summary(report):
    print(f"status: {report['status']}")
    print(f"env_name: {report['summary']['env_name']}")
    artifacts = report.get("evidence", {}).get("artifacts", {})
    present = artifacts.get("present_packages") or []
    missing = artifacts.get("missing_packages") or []
    print("artifacts: " + (" ".join(present) if present else "none"))
    if missing:
        print("missing_artifacts: " + " ".join(missing))
    verification = report.get("evidence", {}).get("verification", {})
    print(
        "verification: "
        f"smoke={verification.get('smoke', 'unknown')} "
        f"upstream_installed={verification.get('upstream_installed', 'unknown')} "
        f"live_state={verification.get('live_state', 'unknown')}"
    )
    for item in report["requirements"]:
        status = "PASS" if item["ok"] else "FAIL"
        print(f"{status} {item['id']}: {item.get('reason', '')}")
    actions = report.get("next_actions", [])
    if actions:
        print("next_actions: " + " ".join(action.get("id", "") for action in actions if action.get("id")))
    else:
        print("next_actions: none")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="monata-env install manifest to audit.")
    parser.add_argument(
        "--check-live",
        action="store_true",
        help="Also inspect current PATH shims and pixi global list --json for the target environment.",
    )
    parser.add_argument(
        "--require-artifacts",
        action="store_true",
        help="Fail when the manifest does not record local package artifacts for every required tool.",
    )
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    return parser.parse_args()


def main():
    args = parse_args()
    report = audit(
        args.manifest.expanduser().resolve(),
        check_live=args.check_live,
        require_artifacts=args.require_artifacts,
    )
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
