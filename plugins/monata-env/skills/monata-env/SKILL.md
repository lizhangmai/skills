---
name: monata-env
description: Set up and validate global circuit-tool dependencies for Monata projects with pixi global. Use when a user asks an agent to install or configure Monata circuit tools; inspect a Monata repository to choose required simulator, schematic, and layout packages; build or reuse ngspice, OpenVAF/OSDI, KLayout, and Xschem packages; install them into a pixi global environment named monata-env; expose tool commands; or validate ngspice, openvaf-r, klayout, and xschem without installing Monata or techlibs.
---

# Monata Env

## Goal

Create or update a pixi global environment named `monata-env` that exposes the
reusable circuit tools used by Monata projects: `ngspice`, `openvaf-r`,
`klayout`, and `xschem`.

This is an AI-native setup skill: inspect first, produce a plan, negotiate
fallbacks with the user through structured `questions` and `next_actions`, run
deterministic helper commands, verify tools directly, and leave a manifest.

Read these references when the relevant branch appears:

- `references/setup-workflow.md`: full planner, local-source, build, install,
  smoke, upstream-installed, manifest, and audit workflow.
- `references/isolated-testing.md`: Singularity/container live validation,
  `--host-pixi-root`, dedicated test images, and tiered live checks.
- `references/error-codes.json`: registered structured `error.code` values.
- `references/circuit-tool-pins.json`: maintained KLayout/Xschem version,
  source ref, source commit, package spec, and recipe checksum pins.
- `schemas/*.schema.json`: JSON contracts for plan, manifest, runbook summary,
  smoke, upstream, audit, `next_actions`, and structured errors.

## Hard Rules

- Do not install Monata.
- Do not install the `monata` Python package.
- Do not bootstrap Monata techlibs.
- Do not create or modify a project-local pixi.toml.
- Do not publish, upload, authenticate, or contact remote production systems.
- Do not build every circuit-toolchain package, run `--all`, or build the Xyce
  recipe stack unless the user explicitly asks for those tools.
- Require an explicit final channel directory such as
  `CONDA_BUILD_OUTPUT_DIR=...`; Do not invent one, and stop before running any
  build, pixi, or install commands if it is missing.
- Missing output directory rule, as a literal execution gate: stop before
  running any build, pixi, or install commands.
- Literal guardrail: before running any build, pixi, or install commands,
  require the user-provided channel directory.
- If `pixi` is missing, stop before environment setup and ask the user to
  install it or approve a specific command. Do not silently install host tools.
- If `rattler-build` is missing and packages must be built, ask before
  installing it as a global CLI; ask before installing it as a global tool.
- Treat setup permission as permission to create or update only the pixi global
  `monata-env` environment and its exposed command shims.

## Core Flow

Start with `scripts/plan_monata_env.py` for nontrivial setup requests:

```bash
python scripts/plan_monata_env.py \
  --root "<project-workspace>" \
  --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
  --write-manifest \
  --format json
```

The plan is the authoritative AI-native setup object. Review `plan.decisions`,
`questions`, `source policy`, `test isolation`, `test_profiles`,
`plan.helper.conda_build_script`, `recommended commands`, and `fallback`
choices with the user before mutating global state. Treat `plan.runbook` as
the execution sequence; runbook items include `depends_on`, `timeout_seconds`,
`stdout_path`, `stderr_path`, `status_path`, and `record_after`.

Prefer `scripts/execute_monata_env_runbook.py` instead of retyping commands:

```bash
python scripts/execute_monata_env_runbook.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --format json
```

After user approval for mutating steps:

```bash
python scripts/execute_monata_env_runbook.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --step build \
  --step install \
  --allow-confirmation-required \
  --format json
```

If the executor returns `next_actions`, do not blindly retry. Present the
machine-readable `decision.options` to the user, then continue by re-planning
or running the suggested command. Each action has `id`, `title`,
`requires_user_input`, `prompt`, optional `command`, optional `evidence`, and
optional `decision`.

For repeatable recovery, use `scripts/replay_monata_env_negotiation.py` to
materialize a selected `next_actions[].decision.options[]` item into concrete
`replan_arguments` after replacing placeholders such as `<klayout-source>`.

## Tool Selection

Inspect the current Monata workspace before choosing packages. Prefer:

```bash
python scripts/detect_monata_tools.py --root "<project-workspace>" --format shell
```

If inspection is inconclusive, use the current baseline package set:
`ngspice openvaf-r klayout xschem`.

KLayout must come from `https://github.com/KLayout/klayout/tree/v0.30.9` through
the bundled recipe. Xschem must come from
`https://codeberg.org/stef_xschem/xschem/src/tag/3.4.7` through the bundled
recipe. Keep recipe sources pinned and checksum-verified by default. When
changing these versions, update `references/circuit-tool-pins.json` and run:

```bash
python scripts/audit_recipe_pins.py --format summary
```

## Channel And Build

If the user-provided channel already contains the detected packages, skip the
build and run `check-channel` so artifacts already present are still recorded
in the manifest:

```bash
python scripts/rattler_channel.py check-channel \
  --recipe-set circuit-toolchain \
  --package ngspice \
  --package openvaf-r \
  --package klayout \
  --package xschem
```

The corresponding runbook step id is `check_channel`.

If packages are missing, build only missing work with `--skip-existing`:

```bash
python scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package ngspice \
  --package openvaf-r \
  --package klayout \
  --package xschem \
  --skip-existing
```

For trusted local source checkouts at `../circuit/klayout` and
`../circuit/xschem`, pass local source paths and required refs:

```bash
python scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package klayout \
  --package xschem \
  --local-source klayout="$(realpath ../circuit/klayout)" \
  --local-source-ref klayout=v0.30.9 \
  --local-source xschem="$(realpath ../circuit/xschem)" \
  --local-source-ref xschem=3.4.7 \
  --skip-existing
```

The helper overlays temporary `source.path` recipes for local source inputs. It
does not hand-copy `.conda` files into the channel and does not require
`conda index`. If a local source is an archive, use `--local-source` without
`--local-source-ref`; the planner reports this as `local_source_archive_trust`.
If git is unavailable in a minimal host or container, validation reports
`git-unavailable` instead of crashing.

## Install

Install detected tools into the pixi global environment named `monata-env` with
the local channel first:

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

Expose each installed executable with the same command name unless the user
asks for a specific alias. Use the detector output instead of hard-coding this
list when the workspace indicates a different package set.

## Verification

Verify the exposed circuit tools directly. Do not import `monata`:

```bash
python scripts/smoke_monata_env_tools.py --format json
```

The smoke checks run `ngspice`, compile OSDI models with `openvaf-r`, write GDS
files through KLayout Ruby/RBA and Python batch APIs, and check
`xschem --version`.

When trusted local upstream source checkouts are available, ask before running
upstream-installed checks:

```bash
python scripts/test_monata_env_upstream.py \
  --format json \
  --profile basic \
  --klayout-source "$(realpath ../circuit/klayout)" \
  --xschem-source "$(realpath ../circuit/xschem)"
```

Use `--profile full` only when the user accepts longer runtime and extra
dependency/display risk. The `upstream-installed` basic profile uses KLayout
upstream test assets plus an installed `strm2txt` wrapper check and an Xschem
upstream create/save test. Full Xschem adds `xschem-full-regression` and may
need Tcl; failures should produce `next_actions` such as
`use-basic-upstream-profile`.

Record verification with `scripts/record_monata_env_session.py`. The manifest
must keep `verification.smoke`, `verification.upstream_installed` when run, and
`verification.audit`.

Common log filenames are `monata-env-build.out`, `monata-env-build.err`,
`monata-env-smoke.err`, and the manifest
`monata-env-install-manifest.json`.

Audit is the final completion gate:

```bash
python scripts/audit_monata_env_manifest.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --check-live \
  --require-artifacts \
  --format json

python scripts/audit_monata_env_manifest.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --check-live \
  --require-artifacts \
  --format summary
```

The summary reports environment name, artifact package coverage, smoke,
upstream, live state from `pixi global list --json`, requirement pass/fail
lines, and remaining `next_actions`.

## Isolated Testing

For isolated live checks, use `scripts/skill_container.py`; read
`references/isolated-testing.md` before running commands that may touch pixi,
package caches, local channels, or Singularity state.

Use `docker://python:3.12-slim` for planner-only container checks unless the
user provides a local `.sif`. The wrapper isolates image/cache state with
`SINGULARITY_CACHEDIR` and `SINGULARITY_TMPDIR`.

Planner options include `--container-image`, `--session-dir`,
`--container-state-dir`, `--test-image-output`, `--host-pixi-root`,
`--conda-build-helper`, and `--live-timeout-seconds`. Generated isolation
choices include `test_image`, `prepare_dedicated`, `remote_prepare_command`,
`host_pixi_bind`, `commands.install_smoke`,
`commands.install_smoke_upstream`, and
`commands.build_install_smoke_upstream`. Use the build+upstream command only
after the user approves a live container build; it runs `check_channel`,
`build`, `install`, `smoke`, `upstream_installed_tests`, and `audit` inside
the isolated state.

For a maintained manual entry point, use
`scripts/run_live_build_validation.py --dry-run` first. It plans
`commands.build_install_smoke_upstream`, writes a host manifest seed, reports
the host/container artifact directories, and can execute the live command after
approval.

The plan's `container.cache_strategy` and `container.live_timeout_seconds`
describe where HOME, pixi, rattler, Singularity cache/tmp, and the outer
wrapper timeout live. Timeout failures return `container-command-timeout`; use
that `next_actions` item to inspect caches/logs, warm the cache, narrow steps,
or retry with a larger timeout.

The dedicated image path uses `scripts/prepare_monata_env_test_image.py`; it
expects python3, git, and pixi. If local Singularity build fails with `fakeroot`
or `/etc/subuid` mapping issues, use `--remote` only when a remote builder is
configured, continue with host pixi bind fallback, or ask for a prebuilt image.

Container preflight uses `--require-command`. Missing tools return
`missing-required-commands` with `choose-container-with-required-commands`.
Registry/network failures can return `use-local-container-image`. Generated
commands may use `--repo-root`, `--prepend-path`, and `bash -c`; use
`bash -c`, not `bash -lc`, when relying on prepended PATH.

## Existing Circuit-Tool Environment

If all required executables are already on `PATH`, still run smoke verification
and record it. Do not install Monata, the `monata` Python package, or techlibs
afterward.

## Optional Packages

Build and install additional circuit packages only when the user explicitly
asks for a workflow that needs them. `xyce` is reserved for explicit Xyce or
deferred backend work.

## Feedback Protocol

If this skill appears wrong, incomplete, or unsafe during execution, produce a
structured feedback report instead of changing external systems:

- Reproduction prompt
- Observed behavior
- Expected behavior
- Suspected cause
- Minimal proposed skill or repository change
- Validation case to add or update
