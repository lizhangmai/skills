---
name: monata-sim-env
description: Set up a local Monata simulation environment with pixi and locally built circuit-tool packages. Use when a user asks an agent to install or configure Monata, inspect a Monata repository to choose required circuit tools, prepare ngspice and OpenVAF/OSDI tooling for Monata simulations, create a reproducible pixi environment for Monata, reuse a local conda channel for circuit tools, or validate that Monata can import and find its external tools.
---

# Monata Simulation Environment

## Goal

Create a project-local pixi environment that can import `monata` from PyPI,
run the current Monata simulator backend through `ngspice`, and provide
OpenVAF/OSDI tooling for model flows.

## Rules

- Keep external simulator binaries outside the Monata Python package.
- Prefer a user-owned local conda channel for circuit-tool packages.
- Require the user prompt to include an explicit `CONDA_BUILD_OUTPUT_DIR=...`
  value, or another explicit final channel directory. Do not invent one.
- If the user did not provide the final channel directory, ask for it and stop
  before running any build, pixi, or install commands.
- Inspect the current Monata workspace before choosing tool packages. Prefer
  `scripts/detect_monata_tools.py` from this skill; otherwise read
  `pyproject.toml`, `README.md`, `src/`, `tests/`, and `docs/`.
- Build the smallest package set needed for the requested Monata workflow. The
  current Monata baseline is `ngspice` plus `openvaf-r`.
- Do not build every circuit-toolchain package, run `--all`, or build the Xyce
  recipe stack unless the user explicitly asks for those tools.
- Do not publish, upload, or authenticate to remote package channels.
- Use the `conda-build` skill for rattler-build details when it is installed.
  If it is not installed, tell the user to install `conda-build` from the same
  `lizhangmai/skills` marketplace or skill source before building packages.

## Workflow

1. Inspect the current directory and decide where the pixi project should live.
   Use an existing project directory when the user is already inside one.
2. Check for `pixi`, `git`, `python3`, and `rattler-build`.
3. Read the user-provided final channel directory and set:

   ```bash
   export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
   ```

4. Detect the required circuit-tool packages from the Monata workspace:

   ```bash
   python3 scripts/detect_monata_tools.py --root "<project-workspace>" --format shell
   ```

   Run this from the installed or cloned `monata-sim-env` skill directory. If a
   Monata workspace cannot be inspected, use the current baseline package set:
   `ngspice openvaf-r`.

5. Build or reuse the detected packages from the `circuit-toolchain` recipe set.
   For the current Monata baseline:

   ```bash
   python3 scripts/rattler_channel.py build \
     --recipe-set circuit-toolchain \
     --package ngspice \
     --package openvaf-r
   ```

   Run this from the installed or cloned `conda-build` skill directory. Use the
   detector output instead of hard-coding this list when the workspace indicates
   a different package set.

6. Create or update the pixi environment with the local channel first:

   ```bash
   pixi init monata-work \
     --channel "file://$CONDA_BUILD_OUTPUT_DIR" \
     --channel https://prefix.dev/conda-forge
   cd monata-work
   pixi add python=3.12 ngspice openvaf-r
   pixi add --pypi monata
   ```

7. Verify:

   ```bash
   pixi run python - <<'PY'
   import shutil
   import monata

   print(monata.__name__)
   print(shutil.which("ngspice"))
   print(shutil.which("openvaf-r"))
   PY
   pixi run ngspice --version
   pixi run openvaf-r --help
   ```

## Existing Simulator Environment

If the user already has the detected circuit tools installed in the active
environment, skip the local channel build and install only Monata:

```bash
python -m pip install monata
python -c "import shutil; print(shutil.which('ngspice')); print(shutil.which('openvaf-r'))"
```

Use this shortcut only when the required executables are already on `PATH` or
under `CONDA_PREFIX/bin`.

## Optional Packages

Build additional circuit packages only when the user explicitly asks for a
workflow that needs them:

- `xyce`: deferred Monata backend work or external Xyce workflows; build the
  recipe stack with `--up-to xyce` only for those explicit requests.
- `monata-techlib`: install from PyPI only when first-party technology metadata
  is needed:

  ```bash
  pixi add --pypi monata-techlib
  ```
