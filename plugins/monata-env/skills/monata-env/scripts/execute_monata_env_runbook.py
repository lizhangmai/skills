#!/usr/bin/env python
"""Execute a monata-env planner runbook and record each executed step."""

import argparse
import hashlib
import json
import shlex
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


def run_command(command, cwd=None, timeout=None):
    command = [str(part) for part in command]
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        timeout_text = f"timed out after {timeout}s"
        stderr = (stderr + "\n" + timeout_text).strip() + "\n"
        return subprocess.CompletedProcess(command, 124, stdout=stdout, stderr=stderr)


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


def write_status(step, status, extra=None):
    path_text = step.get("status_path")
    if not path_text:
        return ""
    path = Path(path_text).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": step.get("id", ""),
        "status": status,
        "command": [str(part) for part in step.get("command", [])],
    }
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    chunks = [
        str(item.get(key, ""))
        for key in ("stdout", "stderr", "record_stdout", "record_stderr")
        if item.get(key)
    ]
    for key in ("stdout_path", "stderr_path"):
        path_text = item.get(key)
        if not path_text:
            continue
        path = Path(path_text)
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8", errors="replace")[-6000:])
    return "\n".join(chunks).lower()


def output_json_payload(item):
    texts = []
    if item.get("stdout"):
        texts.append(item["stdout"])
    stdout_path = item.get("stdout_path")
    if stdout_path:
        path = Path(stdout_path)
        if path.exists():
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    for text in texts:
        text = text.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def payload_next_actions(item):
    payload = output_json_payload(item)
    if not payload:
        return []
    actions = payload.get("next_actions")
    if not isinstance(actions, list):
        return []
    return [
        action
        for action in actions
        if isinstance(action, dict) and action.get("id")
    ]


def payload_error_code(item):
    payload = output_json_payload(item)
    if not payload:
        return ""
    error = payload.get("error")
    if isinstance(error, dict) and error.get("code"):
        return str(error["code"])
    if isinstance(payload.get("error_code"), str):
        return payload["error_code"]
    return ""


def upstream_rerun_command(step, timeout):
    command = [str(part) for part in step.get("original_command") or step.get("command") or []]
    if not command:
        return ""
    if "--timeout" in command:
        timeout_index = command.index("--timeout")
        if timeout_index + 1 < len(command):
            command[timeout_index + 1] = str(timeout)
        else:
            command.append(str(timeout))
    else:
        command.extend(["--timeout", str(timeout)])
    return shlex.join(command)


def keyed_values(command, flag):
    values = {}
    parts = [str(part) for part in command or []]
    for index, part in enumerate(parts):
        if part == flag and index + 1 < len(parts):
            value = parts[index + 1]
        elif part.startswith(f"{flag}="):
            value = part.split("=", 1)[1]
        else:
            continue
        if "=" not in value:
            continue
        package, payload = value.split("=", 1)
        if package and payload:
            values[package] = payload
    return values


def recommended_worktree_path(package, target_ref, source_path):
    safe_ref = str(target_ref).replace("/", "-")
    source_key = hashlib.sha256(str(Path(source_path).expanduser().resolve()).encode("utf-8")).hexdigest()[:8]
    return f"/tmp/monata-sources/{package}-{safe_ref}-{source_key}"


def source_ref_repair_context(step):
    command = step.get("original_command") or step.get("command") or []
    local_sources = keyed_values(command, "--local-source")
    local_source_refs = keyed_values(command, "--local-source-ref")
    context = {}
    for package, source_path in local_sources.items():
        target_ref = local_source_refs.get(package)
        if not target_ref:
            continue
        resolved_source = str(Path(source_path).expanduser().resolve())
        recommended_worktree = recommended_worktree_path(package, target_ref, resolved_source)
        context[package] = {
            "source_path": resolved_source,
            "target_ref": target_ref,
            "recommended_worktree": recommended_worktree,
            "worktree_command": [
                "git",
                "-C",
                resolved_source,
                "worktree",
                "add",
                "--detach",
                recommended_worktree,
                target_ref,
            ],
        }
    return context


def replan_arguments_for_sources(sources):
    args = []
    for package, source_path in sources.items():
        args.extend(["--local-source", f"{package}={source_path}"])
    return args


def next_actions_for_failure(step, item):
    if item.get("status") != "executed":
        return []
    if item.get("returncode") == 0 and item.get("record_returncode") in {None, 0}:
        return []

    text = output_text(item)
    step_id = step.get("id", "")
    evidence = {
        "step_id": step_id,
        "returncode": item.get("returncode"),
        "record_returncode": item.get("record_returncode"),
        "stdout_path": item.get("stdout_path", ""),
        "stderr_path": item.get("stderr_path", ""),
    }
    error_code = payload_error_code(item)
    if error_code:
        evidence["error_code"] = error_code
    actions = payload_next_actions(item)
    if step_id == "upstream_installed_tests" and "xschem-full-regression" in text and "timed out after" in text:
        rerun_command = upstream_rerun_command(step, 900)
        actions.extend(
            [
                {
                    "id": "inspect-xschem-full-regression-timeout",
                    "title": "Inspect Xschem full regression timeout",
                    "requires_user_input": False,
                    "command": rerun_command,
                    "prompt": "The Xschem basic create-save check passed, but xschem-full-regression timed out. Inspect that check output, then rerun full upstream tests with a larger timeout or use the basic profile for routine validation.",
                },
                {
                    "id": "use-basic-upstream-profile",
                    "title": "Re-plan with the basic upstream profile",
                    "requires_user_input": False,
                    "command": "python scripts/plan_monata_env.py --upstream-profile basic ...",
                    "prompt": "The basic upstream profile already validates installed Xschem create/save behavior without the long Xschem regression driver.",
                },
            ]
        )
    if "timed out after" in text:
        actions.append(
            {
                "id": "inspect-timeout-or-cache",
                "title": "Inspect timeout, network, or cache state",
                "requires_user_input": True,
                "prompt": "The runbook step timed out. Inspect the step log, then either retry with a larger timeout, provide a local package/source/cache fallback, or run a narrower step before continuing.",
            }
        )
    if (
        error_code in {"conda-build-helper-missing", "helper-missing"}
        or "rattler_channel.py" in text
        or "no such file" in text
        or "can't open file" in text
    ):
        actions.append(
            {
                "id": "resolve-conda-build-helper",
                "title": "Resolve the conda-build helper path",
                "requires_user_input": False,
                "evidence": evidence,
                "command": "python scripts/plan_monata_env.py --conda-build-helper <path-to-rattler_channel.py> ...",
                "prompt": "The conda-build helper script is missing. Re-run the planner with a valid --conda-build-helper path or refresh the helper checkout.",
            }
        )
    if (
        error_code in {"local-source-ref-mismatch", "local-source-target-ref-missing"}
        or "does not match required ref" in text
        or "target-ref-missing" in text
    ):
        repair_context = source_ref_repair_context(step)
        packages = list(repair_context) or ["klayout", "xschem"]
        worktree_sources = {
            package: item["recommended_worktree"]
            for package, item in repair_context.items()
        }
        corrected_placeholders = {
            package: f"<{package}-source>"
            for package in packages
        }
        archive_placeholders = {
            package: f"<{package}-archive>"
            for package in packages
        }
        actions.append(
            {
                "id": "create-versioned-source-worktree",
                "title": "Use a source checkout at the recipe version",
                "requires_user_input": True,
                "evidence": evidence,
                "decision": {
                    "id": "local_source_ref_repair",
                    "prompt": "How should the local source ref mismatch be repaired?",
                    "default": "create_detached_worktree",
                    "options": [
                        {
                            "id": "create_detached_worktree",
                            "label": "Create detached worktree",
                            "requires_user_input": True,
                            "worktree_commands": {
                                package: item["worktree_command"]
                                for package, item in repair_context.items()
                            },
                            "recommended_sources": worktree_sources,
                            "replan_arguments": replan_arguments_for_sources(worktree_sources),
                            "effect": "Keeps the user's current checkout untouched and builds from the recipe tag.",
                        },
                        {
                            "id": "provide_corrected_source",
                            "label": "Provide corrected checkout",
                            "requires_user_input": True,
                            "replan_arguments": replan_arguments_for_sources(corrected_placeholders),
                            "effect": "Use a user-provided local checkout already at the required upstream ref.",
                        },
                        {
                            "id": "provide_source_archive",
                            "label": "Provide source archive",
                            "requires_user_input": True,
                            "replan_arguments": replan_arguments_for_sources(archive_placeholders),
                            "effect": "Build from a trusted local archive when git ref validation is not possible.",
                        },
                    ],
                },
                "prompt": "The provided source checkout is not at the required upstream ref. Ask whether to create a detached worktree at the required tag or provide a corrected local source path.",
            }
        )
    if (
        error_code in {"source-download-failed", "network-download-failed", "registry-download-failed"}
        or any(token in text for token in ("network timeout", "failed to download", "could not resolve host", "connection timed out"))
    ):
        actions.append(
            {
                "id": "provide-local-source",
                "title": "Use local upstream source checkouts",
                "requires_user_input": True,
                "evidence": evidence,
                "decision": {
                    "id": "source_fallback",
                    "prompt": "How should upstream sources be provided after the network failure?",
                    "default": "provide_local_source",
                    "options": [
                        {
                            "id": "provide_local_source",
                            "label": "Provide local checkout",
                            "requires_user_input": True,
                            "replan_arguments": [
                                "--local-source",
                                "klayout=<klayout-source>",
                                "--local-source",
                                "xschem=<xschem-source>",
                            ],
                            "effect": "Re-run the planner with --local-source package=/path for KLayout and/or Xschem.",
                        },
                        {
                            "id": "provide_source_archive",
                            "label": "Provide source archive",
                            "requires_user_input": True,
                            "replan_arguments": [
                                "--local-source",
                                "klayout=<klayout-archive>",
                                "--local-source",
                                "xschem=<xschem-archive>",
                            ],
                            "effect": "Use a trusted local tar/zip archive when a checkout is unavailable.",
                        },
                        {
                            "id": "retry_network",
                            "label": "Retry network fetch",
                            "requires_user_input": False,
                            "effect": "Retry the build after network/cache/proxy access is restored.",
                        },
                    ],
                },
                "prompt": "Network source download failed. Ask the user for a local KLayout/Xschem source checkout or archive path, then re-run the planner with --local-source.",
            }
        )
    if step_id == "upstream_installed_tests" and "tclsh-missing" in text:
        actions.extend(
            [
                {
                    "id": "install-upstream-test-dependency",
                    "title": "Install or expose Tcl for full upstream tests",
                    "requires_user_input": True,
                    "prompt": "The full Xschem upstream regression needs tclsh. Ask whether to install/expose Tcl in monata-env, run with an env prefix containing tclsh, or use the basic upstream profile.",
                },
                {
                    "id": "use-basic-upstream-profile",
                    "title": "Re-plan with the basic upstream profile",
                    "requires_user_input": False,
                    "command": "python scripts/plan_monata_env.py --upstream-profile basic ...",
                    "prompt": "The basic upstream profile avoids the Xschem Tcl regression driver and still validates installed KLayout/Xschem with smaller upstream subsets.",
                },
            ]
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
        status_path = write_status(step, dependency_result["status"], dependency_result)
        if status_path:
            dependency_result["status_path"] = status_path
        return dependency_result
    reason = should_skip(step, args, explicit_steps)
    item = {
        "id": step.get("id", ""),
    }
    if reason:
        item.update({"status": "skipped", "reason": reason})
        status_path = write_status(step, "skipped", {"reason": reason})
        if status_path:
            item["status_path"] = status_path
        return item
    if args.dry_run:
        item.update({"status": "dry-run", "command": [str(part) for part in step["command"]]})
        status_path = write_status(step, "dry-run", {"command": item["command"]})
        if status_path:
            item["status_path"] = status_path
        return item

    status_path = write_status(step, "running")
    result = run_command(step["command"], cwd=args.cwd, timeout=step.get("timeout_seconds"))
    stdout_path = write_stdout(step, result.stdout)
    stderr_path = write_stderr(step, result.stderr)
    record_result = run_record_after(step, result.returncode, cwd=args.cwd)
    item.update(
        {
            "status": "executed",
            "returncode": result.returncode,
            "stdout_path": stdout_path,
            "stderr_path": stderr_path,
            "status_path": status_path,
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
    if status_path:
        final_status = {
            "returncode": item["returncode"],
            "record_returncode": item["record_returncode"],
            "stdout_path": item["stdout_path"],
            "stderr_path": item["stderr_path"],
        }
        if actions:
            final_status["next_actions"] = actions
        write_status(step, "executed", final_status)
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
