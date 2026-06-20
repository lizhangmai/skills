#!/usr/bin/env python
"""Execute a monata-env planner runbook and record each executed step."""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Input does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Input is not valid JSON: {path}: {exc}") from exc


def load_plan(args):
    if args.plan:
        return load_json(args.plan.expanduser().resolve())
    manifest = load_json(args.manifest.expanduser().resolve())
    plan = manifest.get("plan")
    if not isinstance(plan, dict):
        raise SystemExit(f"Manifest does not contain a plan object: {args.manifest}")
    return plan


def selected_steps(plan, requested_steps):
    runbook = plan.get("runbook")
    if not isinstance(runbook, list):
        raise SystemExit("Plan does not contain a runbook list")
    if not requested_steps:
        return runbook
    requested = set(requested_steps)
    selected = [step for step in runbook if step.get("id") in requested]
    found = {step.get("id") for step in selected}
    missing = sorted(requested - found)
    if missing:
        raise SystemExit("Runbook does not contain requested step(s): " + ", ".join(missing))
    return selected


def should_skip(step, args, explicit_steps):
    if step.get("requires_confirmation") and not args.allow_confirmation_required:
        return "requires-confirmation"
    if not step.get("recommended", False) and not args.include_optional and step.get("id") not in explicit_steps:
        return "not-recommended"
    if not step.get("command"):
        return "no-command"
    return ""


def dependency_satisfied(item):
    if item["status"] == "executed":
        return item["returncode"] == 0 and item.get("record_returncode") in {None, 0}
    if item["status"] == "skipped":
        return item.get("reason") in {"no-command", "not-recommended"}
    return item["status"] == "dry-run"


def dependency_skip(step, results_by_id, selected_ids, explicit_steps):
    for dependency in step.get("depends_on", []):
        if explicit_steps and dependency not in selected_ids:
            continue
        item = results_by_id.get(dependency)
        if item is None:
            return {
                "status": "skipped",
                "reason": "dependency-missing",
                "dependency": dependency,
            }
        if not dependency_satisfied(item):
            return {
                "status": "skipped",
                "reason": "dependency-skipped",
                "dependency": dependency,
            }
    return None


def run_command(command, cwd=None):
    return subprocess.run(
        [str(part) for part in command],
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def write_stdout(step, stdout):
    path_text = step.get("stdout_path")
    if not path_text:
        return ""
    path = Path(path_text).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stdout, encoding="utf-8")
    return str(path)


def write_stderr(step, stderr):
    path_text = step.get("stderr_path")
    if not path_text:
        return ""
    path = Path(path_text).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stderr, encoding="utf-8")
    return str(path)


def substitute_returncode(command, var_name, returncode):
    if not var_name:
        return [str(part) for part in command]
    token = f"${var_name}"
    return [str(returncode) if str(part) == token else str(part) for part in command]


def run_record_after(step, returncode, cwd=None):
    record_after = step.get("record_after")
    if not record_after:
        return None
    command = record_after.get("command")
    if not command:
        return None
    var_name = record_after.get("returncode_var", "")
    result = run_command(substitute_returncode(command, var_name, returncode), cwd=cwd)
    return {
        "returncode": result.returncode,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
    }


def output_text(item):
    return "\n".join(
        str(item.get(key, ""))
        for key in ("stdout", "stderr", "record_stdout", "record_stderr")
        if item.get(key)
    ).lower()


def next_actions_for_failure(step, item):
    if item.get("status") != "executed":
        return []
    if item.get("returncode") == 0 and item.get("record_returncode") in {None, 0}:
        return []

    text = output_text(item)
    step_id = step.get("id", "")
    actions = []
    if "rattler_channel.py" in text or "no such file" in text or "can't open file" in text:
        actions.append(
            {
                "id": "resolve-conda-build-helper",
                "title": "Resolve the conda-build helper path",
                "requires_user_input": False,
                "command": "python scripts/plan_monata_env.py --conda-build-helper <path-to-rattler_channel.py> ...",
                "prompt": "The conda-build helper script is missing. Re-run the planner with a valid --conda-build-helper path or refresh the helper checkout.",
            }
        )
    if "does not match required ref" in text or "target-ref-missing" in text:
        actions.append(
            {
                "id": "create-versioned-source-worktree",
                "title": "Use a source checkout at the recipe version",
                "requires_user_input": True,
                "prompt": "The provided source checkout is not at the required upstream ref. Ask whether to create a detached worktree at the required tag or provide a corrected local source path.",
            }
        )
    if any(token in text for token in ("network timeout", "failed to download", "could not resolve host", "connection timed out")):
        actions.append(
            {
                "id": "provide-local-source",
                "title": "Use local upstream source checkouts",
                "requires_user_input": True,
                "prompt": "Network source download failed. Ask the user for a local KLayout/Xschem source checkout or archive path, then re-run the planner with --local-source.",
            }
        )
    if step_id == "smoke" or "tool-missing" in text or '"reason": "missing"' in text:
        actions.append(
            {
                "id": "inspect-installed-tools",
                "title": "Inspect exposed monata-env tool commands",
                "requires_user_input": False,
                "command": "python scripts/smoke_monata_env_tools.py --format json",
                "prompt": "The installed-tool smoke step failed. Inspect which command is missing or failing before rebuilding or reinstalling monata-env.",
            }
        )
    if not actions:
        actions.append(
            {
                "id": "inspect-step-output",
                "title": "Inspect runbook step output",
                "requires_user_input": False,
                "prompt": "The runbook step failed. Inspect stdout/stderr and decide whether to retry, adjust the plan, or ask the user for a fallback.",
            }
        )
    return actions


def execute_step(step, args, explicit_steps, results_by_id, selected_ids):
    dependency_result = dependency_skip(step, results_by_id, selected_ids, explicit_steps)
    if dependency_result:
        dependency_result["id"] = step.get("id", "")
        return dependency_result
    reason = should_skip(step, args, explicit_steps)
    item = {
        "id": step.get("id", ""),
    }
    if reason:
        item.update({"status": "skipped", "reason": reason})
        return item
    if args.dry_run:
        item.update({"status": "dry-run", "command": [str(part) for part in step["command"]]})
        return item

    result = run_command(step["command"], cwd=args.cwd)
    stdout_path = write_stdout(step, result.stdout)
    stderr_path = write_stderr(step, result.stderr)
    record_result = run_record_after(step, result.returncode, cwd=args.cwd)
    item.update(
        {
            "status": "executed",
            "returncode": result.returncode,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "stdout": result.stdout[-4000:] if not stdout_path else "",
            "stderr": result.stderr[-4000:] if not stderr_path else "",
            "record_returncode": record_result["returncode"] if record_result else None,
        }
    )
    if record_result:
        item["record_stdout"] = record_result["stdout"]
        item["record_stderr"] = record_result["stderr"]
    actions = next_actions_for_failure(step, item)
    if actions:
        item["next_actions"] = actions
    return item


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", type=Path, help="Plan JSON produced by plan_monata_env.py.")
    source.add_argument("--manifest", type=Path, help="Manifest containing a plan object.")
    parser.add_argument("--step", action="append", default=[], help="Run only the named runbook step. Repeatable.")
    parser.add_argument("--allow-confirmation-required", action="store_true", help="Allow steps marked requires_confirmation.")
    parser.add_argument("--include-optional", action="store_true", help="Run non-recommended optional steps.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue after a command or record_after failure.")
    parser.add_argument("--dry-run", action="store_true", help="Show selected runbook commands without executing them.")
    parser.add_argument("--cwd", type=Path, help="Working directory for executed commands.")
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    return parser.parse_args()


def run(args):
    plan = load_plan(args)
    explicit_steps = set(args.step)
    selected = selected_steps(plan, args.step)
    selected_ids = {step.get("id") for step in selected}
    results_by_id = {}
    steps = []
    ok = True
    for step in selected:
        item = execute_step(step, args, explicit_steps, results_by_id, selected_ids)
        steps.append(item)
        results_by_id[item["id"]] = item
        if item["status"] == "executed":
            step_ok = item["returncode"] == 0 and item.get("record_returncode") in {None, 0}
            ok = ok and step_ok
            if not step_ok and not args.continue_on_error:
                break
    next_actions = []
    seen_actions = set()
    for item in steps:
        for action in item.get("next_actions", []):
            action_id = action.get("id", "")
            if action_id in seen_actions:
                continue
            seen_actions.add(action_id)
            next_actions.append(action)
    return {
        "ok": ok,
        "steps": steps,
        "next_actions": next_actions,
    }


def print_summary(summary):
    for step in summary["steps"]:
        status = step["status"].upper()
        if step["status"] == "executed":
            print(f"{status} {step['id']}: rc={step['returncode']} record_rc={step.get('record_returncode')}")
        else:
            print(f"{status} {step['id']}: {step.get('reason', '')}")


def main():
    args = parse_args()
    summary = run(args)
    if args.format == "json":
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print_summary(summary)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
