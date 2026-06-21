# Circuit Toolchain Recipe Set

## Principle

Use the bundled `circuit-toolchain` recipe set when the user needs local conda packages for circuit simulators and Monata-compatible tools. The recipe set must remain usable from a clean machine with this skill, `rattler-build`, and network access to public upstream sources and package channels.

Do not call, clone, or assume any old local `circuit` workspace.

Build the smallest useful package set. For a normal Monata runtime environment,
build or reuse `ngspice`, `openvaf-r`, `klayout`, and `xschem`. Build
Xyce-related packages or the full recipe set only when the user explicitly
requests a workflow that needs those tools.

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
python scripts/rattler_channel.py
```

Before building, set the final artifact channel:

```bash
export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
```

The wrapper writes artifacts to explicit `--output-dir`, `$CONDA_BUILD_OUTPUT_DIR`, or `$CONDA_BLD_PATH`. It does not choose a default final channel. It can check whether selected artifacts already exist in that channel before building. It solves dependencies from `https://prefix.dev/conda-forge`.

For network-constrained users who already have trusted local upstream checkouts
or source archives, the wrapper can build bundled recipes with temporary
local-source overlays:

```bash
python scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package klayout \
  --package xschem \
  --local-source klayout="/abs/path/to/klayout" \
  --local-source-ref klayout=v0.30.9 \
  --local-source xschem="/abs/path/to/xschem" \
  --local-source-ref xschem=3.4.7
```

`--local-source package=path` replaces only the temporary build recipe's
`source:` block with `source.path`. The committed public recipes stay pinned to
remote upstream sources and checksums. The local checkout is trusted user input
and must already be checked out to the recipe's intended upstream version. Use
`--local-source-ref package=ref` to make the helper reject a checkout whose
`HEAD` does not match the expected tag or revision. Artifacts must still be
produced by `rattler-build build --output-dir`; do not hand-copy packages into
a channel.

`--local-source` also accepts trusted `.tar`, `.tar.gz`, `.tar.xz`, and `.zip`
source archives. The helper extracts the archive to a temporary directory and
uses that extracted directory as `source.path`. Do not combine source archives
with `--local-source-ref`; git ref validation only applies to checkouts.

The installed-artifact smoke-test wrapper is:

```bash
python scripts/test_circuit_artifacts.py
```

It creates temporary pixi environments from the local output channel, verifies the main simulator stack, and verifies `trilinos 17.1.0` in a separate environment because `xyce` uses `trilinos ==14.4.0`. Use it after building the full stack; it is broader than the default Monata `ngspice` plus `openvaf-r` setup.

## Commands

List bundled packages:

```bash
python scripts/rattler_channel.py list-recipes --recipe-set circuit-toolchain
```

Render the current Monata baseline without building:

```bash
python scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice --package openvaf-r --package klayout --package xschem --render-only
```

Build the current Monata baseline into the user-provided local channel:

```bash
export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
python scripts/rattler_channel.py check-channel --recipe-set circuit-toolchain --package ngspice --package openvaf-r --package klayout --package xschem
python scripts/rattler_channel.py build --recipe-set circuit-toolchain --package ngspice --package openvaf-r --package klayout --package xschem --skip-existing
```

If `rattler-build` is missing and the user approves pixi-managed global tool
installation, install it before building:

```bash
pixi global install --channel https://prefix.dev/conda-forge rattler-build
rattler-build --version
```

Build Xyce and its recipe dependency set through rattler-build only for explicit
Xyce workflows:

```bash
python scripts/rattler_channel.py build --recipe-set circuit-toolchain --up-to xyce
```

Build every bundled recipe only for maintainer validation or full local-channel
preparation:

```bash
python scripts/rattler_channel.py build --recipe-set circuit-toolchain --all
```

Limit compile parallelism for memory-heavy packages:

```bash
python scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package trilinos-14.4.0 \
  --jobs 4
```

Use the standard conda-forge channel alias when needed:

```bash
python scripts/rattler_channel.py build \
  --recipe-set circuit-toolchain \
  --package ngspice \
  --package openvaf-r \
  --package klayout \
  --package xschem \
  --skip-existing \
  --channel conda-forge
```

Test packages after building:

```bash
python scripts/test_circuit_artifacts.py \
  --output-dir "<user-provided-absolute-conda-channel>" \
  --profile monata-env-baseline
```

The default `monata-env-baseline` smoke installs from `file://<output-dir>`
plus the dependency channel, then checks minimal simulator/layout-tool runs for
`ngspice`, `openvaf-r`, `klayout`, and `xschem`.

Use the complete profile only when the channel intentionally contains the
larger recipe stack:

```bash
python scripts/test_circuit_artifacts.py \
  --output-dir "<user-provided-absolute-conda-channel>" \
  --profile full-toolchain
```

The `full-toolchain` smoke additionally checks Python imports and minimal runs
for `adms`, `vacask`, `xyce`, `xdm`, `monata`, `inspice`, and the separate
Trilinos 17.1.0 environment.

## Package Order

The known package order is:

```text
boost -> adms -> trilinos-14.4.0 -> ngspice -> openvaf-r -> klayout -> xschem -> xdm -> inspice -> monata -> vacask -> xyce -> trilinos-17.1.0
```

`ngspice`, `openvaf-r`, `klayout`, `xschem`, `xdm`, `inspice`, `monata`, and `trilinos-17.1.0` are useful independently. `xyce` depends on `adms` and `trilinos-14.4.0`. `vacask` depends on `boost` and `openvaf-r`.

## Recipe Rules

- Pin upstream source with public `git` URLs and fixed `rev` values or release tarballs with checksums.
- Do not use `source.path` pointing to local `src/` trees in public recipes.
  Use the wrapper's `--local-source package=path` overlay for explicit local
  checkout builds.
- Do not use private channel paths, NAS paths, or machine-specific prefixes.
- Prefer changing recipe dependencies, compiler pins, and build flags over patching upstream source.
- If a patch is required, keep it next to the recipe and document why it is needed.
