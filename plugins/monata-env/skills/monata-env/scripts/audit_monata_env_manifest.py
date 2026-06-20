#!/usr/bin/env python
"""Audit a monata-env setup manifest against the skill's hard requirements."""

import argparse
import json
import shlex
from pathlib import Path


EXPECTED_TOOLS = ["ngspice", "openvaf-r", "klayout", "xschem"]
FORBIDDEN_COMMAND_SNIPPETS = [
    "pixi init",
    "pixi add",
    "pixi run python",
    "bootstrap_monata_techlibs.py",
    "TechlibRegistry",
]


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


def next_actions(requirements, recommendation):
    actions = []
    by_id = {item["id"]: item for item in requirements}
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


def audit(manifest_path):
    manifest = load_json(manifest_path)
    requirements = [
        expected_tool_plan(manifest),
        forbidden_scope(manifest),
        install_succeeded(manifest),
        smoke_passed(manifest),
    ]
    recommendation = upstream_recommendation(manifest)
    ok = all(item["ok"] for item in requirements)
    actions = next_actions(requirements, recommendation)
    status = "ready" if ok else "blocked"
    return {
        "ok": ok,
        "status": status,
        "manifest": str(manifest_path),
        "summary": {
            "env_name": manifest.get("plan", {}).get("env_name", ""),
            "required_tools": EXPECTED_TOOLS,
            "install_ok": requirements[2]["ok"],
            "smoke_ok": requirements[3]["ok"],
            "upstream_installed": recommendation["status"],
        },
        "requirements": requirements,
        "recommendations": [recommendation],
        "next_actions": actions,
    }


def print_summary(report):
    print(f"status: {report['status']}")
    for item in report["requirements"]:
        status = "PASS" if item["ok"] else "FAIL"
        print(f"{status} {item['id']}: {item.get('reason', '')}")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="monata-env install manifest to audit.")
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    return parser.parse_args()


def main():
    args = parse_args()
    report = audit(args.manifest.expanduser().resolve())
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_summary(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
