---
name: conda-build
description: Manage local self-use conda channels and conda package supply-chain workflows with rattler-build. Use when Codex needs to build or render recipes, test existing .conda packages, inspect or extract package contents, generate recipes from PyPI/CRAN/CPAN/LuaRocks, bump recipe versions and checksums, debug builds, create patches through rattler-build debug, rebuild packages for reproducibility, handle variant matrices, configure sandboxed builds, publish or upload packages to channels, or work with the bundled circuit-toolchain recipe set.
---

# Conda Build

## Operating Rules

- Treat this as a `rattler-build` supply-chain skill, not a circuit-only builder.
- Own conda package artifacts, recipe rendering/building/testing/inspection, and
  local channel maintenance. Do not create user application pixi projects or
  install PyPI `monata`; that belongs to `monata-sim-env`.
- Before running a build or rebuild, require the user to provide `CONDA_BUILD_OUTPUT_DIR`, `CONDA_BLD_PATH`, or `--output-dir` for the final artifact channel. Do not invent a default output directory. If the user did not specify one, ask for it before executing build or test commands.
- Check an existing output channel before building when the caller wants reuse.
  Use `check-channel`, then build only missing packages with `--skip-existing`
  unless the user explicitly requests a rebuild.
- Do not silently install host tools. If `rattler-build` is missing, report it.
  When `pixi` is available, offer to run through
  `--rattler-build "pixi exec rattler-build"` only after the user confirms that
  temporary pixi tool download.
- Use `https://prefix.dev/conda-forge` as the default dependency channel unless explicit `--channel` values are given.
- When building for a Monata runtime environment, build only the packages the
  requested workflow needs. The current Monata baseline is `ngspice` plus
  `openvaf-r`; do not use `--all` or `--up-to xyce` unless explicitly asked.
- Keep third-party sources outside the skill. Recipes should fetch public upstream `git` or `url` sources with pinned revisions or checksums.
- Do not publish, upload, or authenticate against remote channels unless the user explicitly asks for that target and provides the needed credentials or trusted environment.
- Read `references/legal-boundaries.md` before advising on redistribution, bundling, or license compatibility.
- Read `references/rattler-build-workflows.md` for nontrivial rattler-build commands beyond local build/render/test.
- Read `references/circuit-toolchain-recipes.md` when using or changing the bundled circuit recipe set.

## Bundled Recipe Sets

The built-in recipe set is `circuit-toolchain`:

```text
assets/recipe-sets/circuit-toolchain/recipes/
assets/recipe-sets/circuit-toolchain/smoke-tests/
```

It includes recipes for `boost`, `adms`, `trilinos-14.4.0`, `ngspice`, `openvaf-r`, `xdm`, `inspice`, `monata`, `vacask`, `xyce`, and `trilinos-17.1.0`.

## Common Commands

List recipe sets and recipes:

```bash
python3 scripts/rattler_channel.py list-recipe-sets
python3 scripts/rattler_channel.py list-recipes --recipe-set circuit-toolchain
```

Render or build the current Monata baseline from the bundled recipe set:

```bash
export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
python3 scripts/rattler_channel.py check-channel --recipe-set circuit-toolchain --package ngspice --package openvaf-r
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice --package openvaf-r --render-only
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice --package openvaf-r --skip-existing
```

If `rattler-build` is missing and the user approves using pixi for the build
tool, pass an explicit command prefix:

```bash
python3 scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package ngspice \
  --package openvaf-r \
  --skip-existing \
  --rattler-build "pixi exec rattler-build"
```

Build larger dependency sets only when explicitly requested:

```bash
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --up-to xyce
```

Render with solve and variant inputs:

```bash
python3 scripts/rattler_channel.py build \
  --recipe-path path/to/recipe \
  --render-only \
  --with-solve \
  --variant-config variants.yaml
```

Test or inspect an existing package:

```bash
python3 scripts/rattler_channel.py test-package --package-file output/linux-64/pkg.conda
python3 scripts/rattler_channel.py inspect-package --package-file output/linux-64/pkg.conda --all
python3 scripts/rattler_channel.py extract-package --package-file output/linux-64/pkg.conda --dest /tmp/pkg-inspect
```

Generate, bump, or reproduce recipes:

```bash
python3 scripts/rattler_channel.py generate-recipe pypi jinja2
python3 scripts/rattler_channel.py bump-recipe --recipe path/to/recipe.yaml --check-only
python3 scripts/rattler_channel.py rebuild --package-file output/linux-64/pkg.conda
```

Use raw rattler-build for workflows that need exact CLI control:

```bash
python3 scripts/rattler_channel.py rattler -- debug setup --recipe path/to/recipe
python3 scripts/rattler_channel.py rattler -- debug create-patch --help
python3 scripts/rattler_channel.py rattler -- publish --help
python3 scripts/rattler_channel.py rattler -- auth --help
```

Smoke-test the bundled circuit artifacts after a build:

```bash
export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
python3 scripts/test_circuit_artifacts.py
```

## Resources

- `scripts/rattler_channel.py`: thin wrapper for local recipe sets, output-channel reuse checks, package testing, package inspection, recipe generation, version bumps, rebuilds, and raw `rattler-build` passthrough.
- `scripts/test_circuit_artifacts.py`: pixi-based installed-artifact smoke tests for the bundled circuit recipe set.
- `references/rattler-build-workflows.md`: command patterns for build, test, publish, recipe maintenance, debug, patch, package inspection, rebuild, CI, sandboxing, and completions.
- `references/circuit-toolchain-recipes.md`: package order, commands, and recipe rules for the bundled circuit recipe set.
- `references/legal-boundaries.md`: redistribution and packaging boundaries for third-party simulator tools.
