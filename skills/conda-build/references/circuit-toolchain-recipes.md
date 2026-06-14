# Circuit Toolchain Recipe Set

## Principle

Use the bundled `circuit-toolchain` recipe set when the user needs local conda packages for circuit simulators and Monata-compatible tools. The recipe set must remain usable from a clean machine with this skill, `rattler-build`, and network access to public upstream sources and package channels.

Do not call, clone, or assume any old local `circuit` workspace.

Build the smallest useful package set. For a normal Monata runtime environment,
build or reuse `ngspice` and `openvaf-r`. Build Xyce-related packages or the
full recipe set only when the user explicitly requests a workflow that needs
those tools.

## Layout

Recipes live under:

```text
assets/recipe-sets/circuit-toolchain/recipes/<package>/recipe.yaml
```

Smoke-test fixtures live under:

```text
assets/recipe-sets/circuit-toolchain/smoke-tests/fixtures/
```

The local channel wrapper is:

```bash
python3 scripts/rattler_channel.py
```

Before building, set the final artifact channel:

```bash
export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
```

The wrapper writes artifacts to explicit `--output-dir`, `$CONDA_BUILD_OUTPUT_DIR`, or `$CONDA_BLD_PATH`. It does not choose a default final channel. It solves dependencies from `https://prefix.dev/conda-forge`.

The installed-artifact smoke-test wrapper is:

```bash
python3 scripts/test_circuit_artifacts.py
```

It creates temporary pixi environments from the local output channel, verifies the main simulator stack, and verifies `trilinos 17.1.0` in a separate environment because `xyce` uses `trilinos ==14.4.0`. Use it after building the full stack; it is broader than the default Monata `ngspice` plus `openvaf-r` setup.

## Commands

List bundled packages:

```bash
python3 scripts/rattler_channel.py list-recipes --recipe-set circuit-toolchain
```

Render the current Monata baseline without building:

```bash
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice --package openvaf-r --render-only
```

Build the current Monata baseline into the user-provided local channel:

```bash
export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice --package openvaf-r
```

Build Xyce and its recipe dependency set through rattler-build only for explicit
Xyce workflows:

```bash
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --up-to xyce
```

Build every bundled recipe only for maintainer validation or full local-channel
preparation:

```bash
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --all
```

Limit compile parallelism for memory-heavy packages:

```bash
python3 scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package trilinos-14.4.0 \
  --jobs 4
```

Use the standard conda-forge channel alias when needed:

```bash
python3 scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package ngspice \
  --package openvaf-r \
  --channel conda-forge
```

Test packages after building:

```bash
python3 scripts/test_circuit_artifacts.py \
  --output-dir "<user-provided-absolute-conda-channel>"
```

The smoke test installs from `file://<output-dir>` plus the dependency channel, then checks Python imports and minimal simulator runs for `ngspice`, `openvaf-r`, `adms`, `vacask`, `xyce`, `xdm`, `monata`, and `inspice`.

## Package Order

The known package order is:

```text
boost -> adms -> trilinos-14.4.0 -> ngspice -> openvaf-r -> xdm -> inspice -> monata -> vacask -> xyce -> trilinos-17.1.0
```

`ngspice`, `openvaf-r`, `xdm`, `inspice`, `monata`, and `trilinos-17.1.0` are useful independently. `xyce` depends on `adms` and `trilinos-14.4.0`. `vacask` depends on `boost` and `openvaf-r`.

## Recipe Rules

- Pin upstream source with public `git` URLs and fixed `rev` values or release tarballs with checksums.
- Do not use `source.path` pointing to local `src/` trees in public recipes.
- Do not use private channel paths, NAS paths, or machine-specific prefixes.
- Prefer changing recipe dependencies, compiler pins, and build flags over patching upstream source.
- If a patch is required, keep it next to the recipe and document why it is needed.
