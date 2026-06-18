#!/usr/bin/env python
"""Render skill harness reports into a structured feedback packet."""

import argparse
import json
from pathlib import Path


def load_reports(reports_dir):
    reports = []
    for path in sorted(Path(reports_dir).glob("*.json")):
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            reports.append(
                {
                    "name": path.stem,
                    "ok": False,
                    "errors": [f"Unable to read report {path}: {exc}"],
                    "case_file": str(path),
                }
            )
    return reports


def render_report(reports):
    lines = [
        "# Skill Feedback Report",
        "",
        "This report is generated from deterministic skill harness output.",
        "Use it as input for a bounded maintainer review or draft PR proposal.",
        "",
    ]

    failed = [report for report in reports if not report.get("ok")]
    passed = [report for report in reports if report.get("ok")]
    lines.append(f"- Passed cases: {len(passed)}")
    lines.append(f"- Failed cases: {len(failed)}")
    lines.append("")

    if not reports:
        lines.append("No harness reports were found.")
        lines.append("")
        return "\n".join(lines)

    if not failed:
        lines.append("No failures were found.")
        lines.append("")
        return "\n".join(lines)

    for report in failed:
        name = report.get("name", "unknown")
        lines.extend(
            [
                f"## {name}",
                "",
                f"- Skill: `{report.get('skill', 'unknown')}`",
                f"- Case file: `{report.get('case_file', 'unknown')}`",
                f"- Provider: `{report.get('provider', 'unknown')}`",
                "",
                "### Reproduction Prompt",
                "",
                "```text",
                str(report.get("prompt", "")).strip(),
                "```",
                "",
                "### Observed Behavior",
                "",
            ]
        )
        errors = report.get("errors") or []
        for error in errors:
            lines.append(f"- {error}")
        lines.extend(
            [
                "",
                "### Expected Behavior",
                "",
                "The case assertions should pass:",
                "",
                "```json",
                json.dumps(report.get("assertions", {}), indent=2, sort_keys=True),
                "```",
                "",
                "### Minimal Proposed Change",
                "",
                "Adjust the relevant `SKILL.md`, script, fixture, or scenario so the expected guardrail is explicit and testable. Keep the change minimal and rerun validation.",
                "",
                "### Validation",
                "",
                "```bash",
                f"python scripts/skill_harness.py run {name}",
                "python scripts/validate.py",
                "```",
                "",
            ]
        )

    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=Path("reports/skill-harness"))
    parser.add_argument("--output", type=Path, default=Path("reports/skill-feedback.md"))
    return parser.parse_args()


def main():
    args = parse_args()
    reports = load_reports(args.reports_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(reports), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
