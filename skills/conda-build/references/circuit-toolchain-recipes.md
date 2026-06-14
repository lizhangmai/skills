# Circuit Toolchain Recipe Set

## Principle

Use the bundled `circuit-toolchain` recipe set when the user needs local conda packages for circuit simulators and Monata-compatible tools. The recipe set must remain usable from a clean machine with this skill, `rattler-build`, and network access to public upstream sources and package channels.

Do not call, clone, or assume any old local `circuit` workspace.

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
export CONDA_BUILD_OUTPUT_DIR="$HOME/.local/share/lizhangmai-conda-channel"
```

By default the wrapper writes artifacts to `$CONDA_BUILD_OUTPUT_DIR`, then `$CONDA_BLD_PATH`, then `$HOME/.local/share/lizhangmai-conda-channel`. It solves dependencies from `https://prefix.dev/conda-forge`.

The installed-artifact smoke-test wrapper is:

```bash
python3 scripts/test_circuit_artifacts.py
```

It creates temporary pixi environments from the local output channel, verifies the main simulator stack, and verifies `trilinos 17.1.0` in a separate environment because `xyce` uses `trilinos ==14.4.0`.

## Commands

List bundled packages:

```bash
python3 scripts/rattler_channel.py list-recipes --recipe-set circuit-toolchain
```

Render one recipe without building:

```bash
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice --render-only
```

Build ngspice into the default local channel:

```bash
export CONDA_BUILD_OUTPUT_DIR="$HOME/.local/share/lizhangmai-conda-channel"
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice
```

Build Xyce and its recipe dependency set through rattler-build:

```bash
python3 scripts/rattler_channel.py build --recipe-set circuit-toolchain --up-to xyce
```

Build every bundled recipe:

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
  --up-to xyce \
  --channel conda-forge
```

Test packages after building:

```bash
python3 scripts/test_circuit_artifacts.py \
  --output-dir "$HOME/.local/share/lizhangmai-conda-channel"
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
