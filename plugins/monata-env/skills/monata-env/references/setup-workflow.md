# Monata Env Setup Workflow

Use this reference after `SKILL.md` routes a setup request into the planner or
runbook path.

## Planner

Run `scripts/plan_monata_env.py` before mutating global state. The planner
captures detected packages, channel reuse, local-source status, recommended
commands, user decisions, test profiles, runbook steps, helper paths, and the
manifest location.

When local KLayout/Xschem checkouts are provided, pass one
`--local-source package=path` per checkout. For git checkouts, pass
`--local-source-ref klayout=v0.30.9` or `--local-source-ref xschem=3.4.7` so
the build helper rejects mismatched checkouts. For source archives, omit
`--local-source-ref`; archives are trusted local inputs and cannot be ref
validated.

Use `--session-dir` for transient logs/manifests when live validation should
inspect a final package channel without overwriting that channel's final
manifest. Use `--overwrite-manifest` only when the user explicitly wants to
discard recorded evidence.

## Runbook

Prefer `scripts/execute_monata_env_runbook.py` over manual command execution.
It enforces `depends_on`, writes `status_path`, captures stdout/stderr, runs
`record_after`, and returns `next_actions` on diagnosed failures.

Recommended default:

```bash
python scripts/execute_monata_env_runbook.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --format json
```

Mutating steps require explicit user approval:

```bash
python scripts/execute_monata_env_runbook.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --step build \
  --step install \
  --allow-confirmation-required \
  --format json
```

If a step fails, use its structured `next_actions` rather than pasting raw logs
back to the user. Common branches are local source repair, helper path repair,
network/source fallback, missing tools, full upstream timeout, or audit repair.

To replay a negotiated option without hand-editing arguments, run:

```bash
python scripts/replay_monata_env_negotiation.py \
  --summary /path/to/failed-summary.json \
  --action provide-local-source \
  --option provide_local_source \
  --replace '<klayout-source>=/path/to/klayout' \
  --replace '<xschem-source>=/path/to/xschem' \
  --format json
```

Append the returned `replan_arguments` to the next `plan_monata_env.py` call.

## Build And Reuse

Before changing bundled KLayout/Xschem recipe versions, update
`references/circuit-tool-pins.json` and run:

```bash
python scripts/audit_recipe_pins.py --format summary
```

The audit compares the maintained pins against `plan_monata_env.py` planner
specs and the circuit-toolchain rattler recipes.

Run `check-channel` first. When artifacts already exist, skip build but still
record artifacts with the `check_channel` step so audit can prove package
coverage.

Build only missing packages and use `--skip-existing`. Do not run `--all`
unless the user explicitly asks for the full circuit-toolchain.

If a checkout is not at the recipe ref, do not change it in place. Use the
planner/executor-provided `worktree_commands`, `recommended_sources`, and
`replan_arguments`. Temporary worktree paths include a source-path hash to
avoid collisions.

## Install

Install with local channel first, then conda-forge:

```bash
pixi global install --environment monata-env \
  --channel "file://$CONDA_BUILD_OUTPUT_DIR" \
  --channel https://prefix.dev/conda-forge \
  --expose ngspice=ngspice \
  --expose openvaf-r=openvaf-r \
  --expose klayout=klayout \
  --expose xschem=xschem \
  ngspice openvaf-r klayout=0.30.9 xschem=3.4.7
```

Use detected package/exposure lists when they differ from the baseline.

## Verification And Audit

Smoke verification must exercise tools directly and never import Monata. Use
`scripts/smoke_monata_env_tools.py --format json`, record it as
`verification.smoke`, and then audit the manifest.

When trusted local upstream checkouts are available, offer the optional
upstream-installed profile. `basic` is the default; `full` is opt-in due to
runtime and dependency/display risk.

The final audit should run with `--check-live --require-artifacts`. The summary
form is the user-facing report:

```bash
python scripts/audit_monata_env_manifest.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --check-live \
  --require-artifacts \
  --format summary
```
