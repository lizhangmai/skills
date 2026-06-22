#!/usr/bin/env python
"""Validate monata-env JSON payloads against versioned schema contracts."""

import argparse
import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = SCRIPT_DIR.parent / "schemas"
SCHEMAS = {
    "audit-report": "audit-report.schema.json",
    "error": "error.schema.json",
    "manifest": "manifest.schema.json",
    "next-action": "next-action.schema.json",
    "plan": "plan.schema.json",
    "runbook-summary": "runbook-summary.schema.json",
    "tool-smoke": "tool-smoke.schema.json",
    "upstream-tests": "upstream-tests.schema.json",
}


class ContractError(Exception):
    pass


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path}: invalid JSON: {exc}") from exc


def type_names(type_spec):
    if isinstance(type_spec, list):
        return type_spec
    if isinstance(type_spec, str):
        return [type_spec]
    return []


def is_type(value, type_name):
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if type_name == "null":
        return value is None
    raise ContractError(f"unsupported schema type {type_name!r}")


def validate_value(value, schema, path="$"):
    errors = []
    allowed_types = type_names(schema.get("type"))
    if allowed_types and not any(is_type(value, type_name) for type_name in allowed_types):
        errors.append(f"{path}: expected {' or '.join(allowed_types)}, got {type(value).__name__}")
        return errors

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: expected one of {schema['enum']!r}, got {value!r}")

    if isinstance(value, str) and "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: expected string length >= {schema['minLength']}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(value) < min_items:
            errors.append(f"{path}: expected at least {min_items} item(s)")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_value(item, item_schema, f"{path}[{index}]"))

    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, property_schema in properties.items():
                if key in value:
                    errors.extend(validate_value(value[key], property_schema, f"{path}.{key}"))
        if schema.get("additionalProperties") is False:
            allowed = set(properties)
            for key in value:
                if key not in allowed:
                    errors.append(f"{path}: unexpected property {key!r}")

    return errors


def schema_path(kind):
    if kind not in SCHEMAS:
        choices = ", ".join(sorted(SCHEMAS))
        raise ContractError(f"unknown contract kind {kind!r}; expected one of: {choices}")
    return SCHEMA_DIR / SCHEMAS[kind]


def validate_contract(kind, file_path):
    schema = load_json(schema_path(kind))
    payload = load_json(file_path)
    errors = validate_value(payload, schema)
    if errors:
        raise ContractError("\n".join(errors))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(SCHEMAS), required=True)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--format", choices=("summary", "json"), default="summary")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        validate_contract(args.kind, args.file.expanduser().resolve())
    except ContractError as exc:
        if args.format == "json":
            print(json.dumps({"ok": False, "kind": args.kind, "file": str(args.file), "error": str(exc)}, indent=2))
        else:
            print(f"FAIL {args.kind}: {exc}")
        return 1
    if args.format == "json":
        print(json.dumps({"ok": True, "kind": args.kind, "file": str(args.file)}, indent=2))
    else:
        print(f"PASS {args.kind}: {args.file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
