---
name: monata-env
description: Set up and validate global circuit-tool dependencies for Monata projects with pixi global. Use when a user asks an agent to install or configure Monata circuit tools; inspect a Monata repository to choose required simulator, schematic, and layout packages; build or reuse ngspice, OpenVAF/OSDI, KLayout, and Xschem packages; install them into a pixi global environment named monata-env; expose tool commands; or validate ngspice, openvaf-r, klayout, and xschem without installing Monata or techlibs.
---

# Monata Env

## Goal

Create or update a pixi global environment named `monata-env` that exposes the
circuit tools used by Monata projects. The default tool set is `ngspice`,
`openvaf-r`, `klayout`, and `xschem`.

This skill intentionally does not install the Monata package while Monata is
still under active development. It may install Python, Ruby, Qt, and other
runtime dependencies needed by tools such as KLayout. It keeps tooling reusable
across projects instead of creating a new pixi environment in each project
directory.

## Rules

- Do not install Monata.
- Do not install the `monata` Python package.
- Do not bootstrap Monata techlibs.
- Do not create or modify a project-local pixi.toml.
- Keep external simulator binaries outside the Monata Python package.
- Own Monata circuit-tool orchestration: inspect the workspace, choose required
  circuit-tool packages, reuse or request package builds, install those tools
  into the pixi global `monata-env` environment, expose tool commands, and
  verify the tool commands directly.
- Treat conda-build recipe helpers as an implementation detail. Do not make
  the user install or invoke a second skill for the standard Monata circuit
  tool setup.
- Prefer a user-owned local conda channel for circuit-tool packages.
- Require the user prompt to include an explicit `CONDA_BUILD_OUTPUT_DIR=...`
  value, or another explicit final channel directory. Do not invent one.
- If the user did not provide the final channel directory, ask for it and stop
  before running any build, pixi, or install commands.
- Inspect the current Monata workspace before choosing tool packages. Prefer
  `scripts/detect_monata_tools.py` from this skill; otherwise read
  `pyproject.toml`, `README.md`, `src/`, `tests/`, and `docs/`.
- Build the smallest package set needed for the requested Monata workflow. The
  current Monata baseline is `ngspice`, `openvaf-r`, `klayout`, and
  `xschem`.
- Build KLayout from the public upstream source
  `https://github.com/KLayout/klayout/tree/v0.30.9` through the bundled
  `klayout` recipe. Keep the recipe source remote, pinned to the `v0.30.9`
  commit, and checksum-verified; do not depend on a local KLayout checkout.
- Build Xschem from the public upstream source
  `https://codeberg.org/stef_xschem/xschem/src/tag/3.4.7` through the bundled
  `xschem` recipe. Keep the recipe source remote, pinned to the `3.4.7`
  commit, and checksum-verified; do not depend on a local Xschem checkout.
- If the user-provided channel already contains the detected packages, skip the
  build and do not require `rattler-build`.
- Do not build every circuit-toolchain package, run `--all`, or build the Xyce
  recipe stack unless the user explicitly asks for those tools.
- Do not silently install host tools. If `pixi` is missing, stop before
  environment setup and ask the user to install it or approve a specific
  install command. If `rattler-build` is missing and packages must be built,
  ask before installing it as a global CLI with
  `pixi global install --channel https://prefix.dev/conda-forge
  rattler-build`.
- Treat the setup request as permission to create or update only the pixi
  global `monata-env` environment and its exposed command shims.
- Do not publish, upload, or authenticate to remote package channels.
- If the conda-build helper is not available locally, clone or update
  `https://github.com/lizhangmai/skills` into
  `$HOME/.cache/monata-env/skills` and run the helper from there. This keeps
  `monata-env` as the only user-facing skill for circuit-tool setup.

## Workflow

1. Inspect the current directory as the Monata workspace. Do not create a
   nested project directory and do not initialize pixi in the project.
2. Check for `git` and `pixi`. If `pixi` is missing, stop before environment
   setup and ask the user to install pixi or approve a specific install
   command.
3. Read the user-provided final channel directory and set:

   ```bash
   export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
   ```

4. Detect the required circuit-tool packages from the Monata workspace:

   ```bash
   python scripts/detect_monata_tools.py --root "<project-workspace>" --format shell
   ```

   Run this from the installed or cloned `monata-env` skill directory. If a
   Monata workspace cannot be inspected, use the current baseline package set:
   `ngspice openvaf-r klayout xschem`.

5. Resolve the conda-build helper. Prefer a local sibling checkout:

   ```text
   plugins/conda-build/skills/conda-build/scripts/rattler_channel.py
   ```

   If it is not available, create/update a helper checkout:

   ```bash
   mkdir -p "$HOME/.cache/monata-env"
   git clone --depth 1 https://github.com/lizhangmai/skills.git \
     "$HOME/.cache/monata-env/skills"
   ```

   If the checkout already exists, run `git -C ... pull --ff-only`.

6. Check the user-provided channel. If all detected packages are present, skip
   the build step:

   ```bash
   python scripts/rattler_channel.py check-channel \
     --recipe-set circuit-toolchain \
     --package ngspice \
     --package openvaf-r \
     --package klayout \
     --package xschem
   ```

   Run this from the resolved `conda-build` skill directory. Use the detector
   output instead of hard-coding this list when the workspace indicates a
   different package set.

7. If any detected package is missing, build only missing work from the
   `circuit-toolchain` recipe set and let existing artifacts be reused:

   ```bash
   python scripts/rattler_channel.py build \
     --recipe-set circuit-toolchain \
     --package ngspice \
     --package openvaf-r \
     --package klayout \
     --package xschem \
     --skip-existing
   ```

   If `rattler-build` is missing but `pixi` is available, ask before installing
   it globally:

   ```bash
   pixi global install --channel https://prefix.dev/conda-forge rattler-build
   rattler-build --version
   ```

8. Install the detected circuit tools into the pixi global environment named
   `monata-env`. Put the local channel first, then conda-forge:

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

   Use the detector output instead of hard-coding this list when the workspace
   indicates a different package set. Expose each installed executable with the
   same command name unless the user asks for a specific alias.

9. Verify the exposed circuit tools directly. Do not import `monata`:

   ```bash
   ngspice --version
   openvaf-r --help
   klayout -v
   xschem --version
   ```

## Existing Circuit-Tool Environment

If the detected circuit tools are already available on `PATH`, still verify
the commands directly and report that no pixi global install was needed:

```bash
ngspice --version
openvaf-r --help
klayout -v
xschem --version
```

Use this shortcut only when all required executables are already on `PATH`.
Do not install Monata, the `monata` Python package, or techlibs afterward.

## Optional Packages

Build and install additional circuit packages only when the user explicitly
asks for a workflow that needs them:

- `xyce`: deferred Monata backend work or external Xyce workflows; build the
  recipe stack with `--up-to xyce` only for those explicit requests.

## Isolated Testing

When validating this skill with the repository harness, prefer static cases for
ordinary development and use the Singularity provider only for explicit live
checks. Live checks must run with a temporary home and pixi cache so they do
not mutate the user's current environment.

The expected isolation variables are:

```bash
HOME=/tmp/skill-home
PIXI_HOME=/tmp/skill-home/.pixi
XDG_CACHE_HOME=/tmp/skill-home/.cache
RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler
CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel
```

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
