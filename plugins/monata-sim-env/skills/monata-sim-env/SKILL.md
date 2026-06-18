---
name: monata-sim-env
description: One-click set up and validate a complete local Monata simulation environment. Use when a user asks an agent to install or configure Monata; inspect a Monata repository to choose required circuit tools; build or reuse ngspice and OpenVAF/OSDI packages; create a reproducible pixi environment; bootstrap PTM_MG and PTM_BULK techlibs under MONATA_HOME; generate the Monata README demo; run the demo successfully; or validate that Monata can import, find external tools, discover techlibs, and execute an ngspice simulation.
---

# Monata Simulation Environment

## Goal

Create a project-local pixi environment that can import `monata` from PyPI,
run the current Monata simulator backend through `ngspice`, provide
OpenVAF/OSDI tooling for model flows, install Monata PTM techlibs under
`MONATA_HOME`, generate the README demo, and run that demo successfully.

## Rules

- Keep external simulator binaries outside the Monata Python package.
- Own Monata user-environment orchestration: detect required tools, reuse or
  request package builds, create/update the project pixi environment, install
  PyPI `monata`, bootstrap techlibs, generate the demo, and verify runtime
  commands.
- Treat conda-build recipe helpers as an implementation detail. Do not make
  the user install or invoke a second skill for the standard Monata setup.
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
- If the user-provided channel already contains the detected packages, skip the
  build and do not require `rattler-build`.
- Do not build every circuit-toolchain package, run `--all`, or build the Xyce
  recipe stack unless the user explicitly asks for those tools.
- Do not silently install host tools. If `pixi` is missing, stop and ask the
  user to install it or approve a specific install command. If `rattler-build`
  is missing and packages must be built, ask before installing it as a global
  CLI with `pixi global install --channel https://prefix.dev/conda-forge
  rattler-build`.
- Treat the setup request as permission to create/update the project pixi
  environment, install project dependencies, download official public PTM model
  cards, and download the VA-Models BSIM-CMG source subset into the user's
  `MONATA_HOME`. It is not permission to install global or host-level tools.
- Do not use unofficial model mirrors. Do not redistribute downloaded PTM or
  VA-Models resources from this skill or the Monata package.
- Do not publish, upload, or authenticate to remote package channels.
- If the conda-build helper is not available locally, clone or update
  `https://github.com/lizhangmai/skills` into
  `$MONATA_HOME/downloads/skills/skills` and run the helper from
  there. This keeps `monata-sim-env` as the only user-facing skill.

## Workflow

1. Inspect the current directory and decide where the pixi project should live.
   Use the current directory when the user is already inside the intended
   project directory, including directories named `test`. Do not create a
   nested `monata-work/` directory unless the user explicitly asks for a new
   subdirectory.
2. Check for `python`, `git`, and `pixi`. If `pixi` is missing, stop before
   environment setup and ask the user to install pixi or approve a specific
   install command.
3. Determine `MONATA_HOME`:
   - Use a user-provided `MONATA_HOME=...` first.
   - Otherwise use the environment variable.
   - Otherwise use `~/.monata`.

   Export it for all later commands:

   ```bash
   export MONATA_HOME="<monata-home>"
   ```

4. Read the user-provided final channel directory and set:

   ```bash
   export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
   ```

5. Detect the required circuit-tool packages from the Monata workspace:

   ```bash
   python scripts/detect_monata_tools.py --root "<project-workspace>" --format shell
   ```

   Run this from the installed or cloned `monata-sim-env` skill directory. If a
   Monata workspace cannot be inspected, use the current baseline package set:
   `ngspice openvaf-r`.

6. Resolve the conda-build helper. Prefer a local sibling checkout:

   ```text
   plugins/conda-build/skills/conda-build/scripts/rattler_channel.py
   ```

   If it is not available, create/update a helper checkout:

   ```bash
   mkdir -p "$MONATA_HOME/downloads/skills"
   git clone --depth 1 https://github.com/lizhangmai/skills.git \
     "$MONATA_HOME/downloads/skills/skills"
   ```

   If the checkout already exists, run `git -C ... pull --ff-only`.

7. Check the user-provided channel. If all detected packages are present, skip
   the build step:

   ```bash
   python scripts/rattler_channel.py check-channel \
     --recipe-set circuit-toolchain \
     --package ngspice \
     --package openvaf-r
   ```

   Run this from the resolved `conda-build` skill directory. Use the detector
   output instead of hard-coding this list when the workspace indicates a
   different package set.

8. If any detected package is missing, build only missing work from the
   `circuit-toolchain` recipe set and let existing artifacts be reused:

   ```bash
   python scripts/rattler_channel.py build \
     --recipe-set circuit-toolchain \
     --package ngspice \
     --package openvaf-r \
     --skip-existing
   ```

   If `rattler-build` is missing but `pixi` is available, ask before installing
   it globally:

   ```bash
   pixi global install --channel https://prefix.dev/conda-forge rattler-build
   rattler-build --version
   ```

9. Create or update the pixi environment in the selected project directory with
   the local channel first. If `pixi.toml` already exists, skip `pixi init` and
   run only the `pixi add` commands. If it does not exist, initialize the
   current directory:

   ```bash
   pixi init . \
     --channel "file://$CONDA_BUILD_OUTPUT_DIR" \
     --channel https://prefix.dev/conda-forge
   pixi add python=3.12 ngspice openvaf-r
   pixi add --pypi "monata>=0.1.1"
   ```

10. Bootstrap Monata PTM techlibs from this skill. Run this through pixi so
    verification can import the installed Monata package:

    ```bash
    pixi run python "<monata-sim-env-skill-dir>/scripts/bootstrap_monata_techlibs.py" \
      --monata-home "$MONATA_HOME"
    ```

    This installs `PTM_MG` and `PTM_BULK` under `$MONATA_HOME/techlibs`. Reruns
    skip already installed techlibs unless `--force` is used.

11. Generate and run the README demo:

    ```bash
    pixi run python "<monata-sim-env-skill-dir>/scripts/write_monata_readme_demo.py" \
      --project-dir "<project-workspace>" \
      --monata-home "$MONATA_HOME" \
      --force \
      --run
    ```

    The script writes `monata_readme_demo.py`, creates a disposable
    `monata_readme_demo_work/` library directory, verifies `PTM_BULK` and
    `PTM_MG` discovery, runs the ngspice DC demo, and prints the `vout`
    waveform.

12. Verify the final environment explicitly:

    ```bash
    MONATA_HOME="$MONATA_HOME" pixi run python - <<'PY'
    import os
    import shutil
    import monata
    from monata.techlib.registry import TechlibRegistry

    print(monata.__name__)
    print(shutil.which("ngspice"))
    print(shutil.which("openvaf-r"))
    print(TechlibRegistry(search_paths=[os.path.join(os.environ["MONATA_HOME"], "techlibs")], auto_discover=False).list_techlibs())
    PY
    pixi run ngspice --version
    pixi run openvaf-r --help
    ```

## Existing Simulator Environment

If the user already has the detected circuit tools installed in the active
environment, skip the local channel build and install only Monata:

```bash
python -m pip install "monata>=0.1.1"
python -c "import shutil; print(shutil.which('ngspice')); print(shutil.which('openvaf-r'))"
```

Use this shortcut only when the required executables are already on `PATH` or
under `CONDA_PREFIX/bin`. Still run `bootstrap_monata_techlibs.py` and
`write_monata_readme_demo.py --run` afterward.

## Optional Packages

Build additional circuit packages only when the user explicitly asks for a
workflow that needs them:

- `xyce`: deferred Monata backend work or external Xyce workflows; build the
  recipe stack with `--up-to xyce` only for those explicit requests.

## Feedback Protocol

If this skill appears wrong, incomplete, or unsafe during execution, produce a
structured feedback report instead of changing external systems:

- Reproduction prompt
- Observed behavior
- Expected behavior
- Suspected cause
- Minimal proposed skill or repository change
- Validation case to add or update

Do not push, open pull requests, publish artifacts, authenticate to remote
services, or contact external production systems unless the user explicitly
asks and the current environment provides authorized credentials.
