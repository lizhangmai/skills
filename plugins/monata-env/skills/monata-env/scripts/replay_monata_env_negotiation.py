#!/usr/bin/env python
"""Materialize a selected monata-env next_action option for replay."""

import argparse
import json
import re
from pathlib import Path


PLACEHOLDER_RE = re.compile(r"<[^>]+>")


def load_summary(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Summary is not valid JSON: {path}: {exc}") from exc


def all_actions(summary):
    actions = list(summary.get("next_actions") or [])
    for step in summary.get("steps") or []:
        actions.extend(step.get("next_actions") or [])
    return actions


def find_action(summary, action_id):
    for action in all_actions(summary):
        if action.get("id") == action_id:
            return action
    raise SystemExit(f"Action not found in summary: {action_id}")


def find_option(action, option_id):
    decision = action.get("decision") or {}
    for option in decision.get("options") or []:
        if option.get("id") == option_id:
            return option
    raise SystemExit(f"Option not found for action {action.get('id', '')}: {option_id}")


def parse_replacements(values):
    replacements = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--replace must use placeholder=value syntax: {value}")
        key, replacement = value.split("=", 1)
        if not key.startswith("<") or not key.endswith(">"):
            raise SystemExit(f"--replace key must be a placeholder like <name>: {value}")
        replacements[key] = replacement
    return replacements


def materialize_arguments(arguments, replacements):
    materialized = []
    for argument in arguments:
        text = str(argument)
        for key, replacement in replacements.items():
            text = text.replace(key, replacement)
        unresolved = PLACEHOLDER_RE.findall(text)
        if unresolved:
            raise SystemExit(f"Unresolved placeholder(s) in {argument!r}: {', '.join(unresolved)}")
        materialized.append(text)
    return materialized


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True, help="JSON summary from execute_monata_env_runbook.py.")
    parser.add_argument("--action", required=True, help="next_actions[].id to replay.")
    parser.add_argument("--option", required=True, help="decision.options[].id to materialize.")
    parser.add_argument(
        "--replace",
        action="append",
        default=[],
        help="Placeholder replacement such as <klayout-source>=/path/to/source. Repeatable.",
    )
    parser.add_argument("--format", choices=("json", "summary"), default="summary")
    return parser.parse_args()


def run(args):
    summary = load_summary(args.summary.expanduser().resolve())
    action = find_action(summary, args.action)
    option = find_option(action, args.option)
    replan_arguments = materialize_arguments(option.get("replan_arguments") or [], parse_replacements(args.replace))
    return {
        "ok": True,
        "summary": str(args.summary),
        "action_id": action["id"],
        "option_id": option["id"],
        "replan_arguments": replan_arguments,
        "effect": option.get("effect", ""),
    }


def main():
    args = parse_args()
    result = run(args)
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(" ".join(result["replan_arguments"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
