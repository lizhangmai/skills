---
name: monata-sim-env
description: Set up a local Monata simulation environment with pixi and locally built circuit-tool packages. Use when a user asks an agent to install or configure Monata, prepare ngspice for Monata simulations, create a reproducible pixi environment for Monata, reuse a local conda channel for circuit tools, or validate that Monata can import and find ngspice.
---

# Monata Simulation Environment

## Goal

Create a project-local pixi environment that can import `monata` from PyPI and
run the current Monata simulator backend through an `ngspice` executable.

## Rules

- Keep external simulator binaries outside the Monata Python package.
- Prefer a user-owned local conda channel for circuit-tool packages.
- Before building, ask the user to set or confirm `CONDA_BUILD_OUTPUT_DIR`.
- Use `$HOME/.local/share/monata-conda-channel` when the user does not choose a
  persistent output directory.
- Do not publish, upload, or authenticate to remote package channels.
- Use the `conda-build` skill for rattler-build details when it is installed.
  If it is not installed, tell the user to install `conda-build` from the same
  `lizhangmai/skills` marketplace or skill source before building packages.

## Workflow

1. Inspect the current directory and decide where the pixi project should live.
   Use an existing project directory when the user is already inside one.
2. Check for `pixi`, `git`, `python3`, and `rattler-build`.
3. Set or confirm:

   ```bash
   export CONDA_BUILD_OUTPUT_DIR="$HOME/.local/share/monata-conda-channel"
   ```

4. Build or reuse `ngspice` from the `circuit-toolchain` recipe set:

   ```bash
   python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice
   ```

   Run this from the installed or cloned `conda-build` skill directory.

5. Create or update the pixi environment with the local channel first:

   ```bash
   pixi init monata-work \
     --channel "file://$CONDA_BUILD_OUTPUT_DIR" \
     --channel https://prefix.dev/conda-forge
   cd monata-work
   pixi add python=3.12 ngspice
   pixi add --pypi monata
   ```

6. Verify:

   ```bash
   pixi run python - <<'PY'
   import shutil
   import monata

   print(monata.__name__)
   print(shutil.which("ngspice"))
   PY
   pixi run ngspice --version
   ```

## Existing Simulator Environment

If the user already has `ngspice` or another required simulator installed in
the active environment, skip the local channel build and install only Monata:

```bash
python -m pip install monata
python -c "import monata, shutil; print(shutil.which('ngspice'))"
```

Use this shortcut only when the simulator executable is already on `PATH` or
under `CONDA_PREFIX/bin`.

## Optional Packages

Build additional circuit packages only when the workflow needs them:

- `openvaf-r`: Verilog-A to OSDI preparation.
- `xyce`: Xyce workflows; build the recipe stack with `--up-to xyce`.
- `monata-techlib`: install from PyPI only when first-party technology metadata
  is needed:

  ```bash
  pixi add --pypi monata-techlib
  ```
