# Rattler-Build Workflows

## Local Channel Setup

Use the skill wrapper for repeatable local workflows:

```bash
export CONDA_BUILD_OUTPUT_DIR="<user-provided-absolute-conda-channel>"
python3 scripts/rattler_channel.py build --recipe-path path/to/recipe
```

Defaults:

- Output channel: explicit `--output-dir`, `$CONDA_BUILD_OUTPUT_DIR`, or `$CONDA_BLD_PATH`
- Dependency channel: `https://prefix.dev/conda-forge`

Before build or rebuild commands, require the user to set `CONDA_BUILD_OUTPUT_DIR` or provide `--output-dir` for the final artifact channel. If the user did not specify one, ask for it before running build or test commands. Pass explicit `--output-dir` and repeated `--channel` values when the user needs a different local channel or dependency source. Use `/tmp` only for temporary render, debug, or inspection work, not as the long-lived artifact channel.

For bundled recipe sets, check a reusable channel before building when the
caller wants to avoid rebuilding existing artifacts:

```bash
python3 scripts/rattler_channel.py check-channel --package pkg-name
python3 scripts/rattler_channel.py build --recipe-path path/to/recipe --skip-existing
```

Do not silently install `rattler-build`. If it is missing and the user approves
pixi-managed global tool installation, install it with pixi before building:

```bash
pixi global install --channel https://prefix.dev/conda-forge rattler-build
rattler-build --version
```

## Build, Render, and Variants

Render without building:

```bash
python3 scripts/rattler_channel.py build --recipe-path path/to/recipe --render-only
```

Render and solve dependencies:

```bash
python3 scripts/rattler_channel.py build \
  --recipe-path path/to/recipe \
  --render-only \
  --with-solve
```

Use variant matrices:

```bash
python3 scripts/rattler_channel.py build \
  --recipe-path path/to/recipe \
  --variant python=3.12,3.13 \
  --variant-config variants.yaml
```

Use `--sandbox` for stricter build isolation. Add `--allow-network` only when the build script legitimately needs network access after source fetch.

## Test Existing Packages

Test an already built package in a temporary test environment:

```bash
python3 scripts/rattler_channel.py test-package --package-file output/linux-64/pkg.conda
```

Use this before publishing or before treating a local channel as usable by downstream pixi/conda environments.

## Inspect and Extract Packages

Inspect metadata, file lists, about data, and run exports:

```bash
python3 scripts/rattler_channel.py inspect-package --package-file output/linux-64/pkg.conda --all
python3 scripts/rattler_channel.py inspect-package --package-file output/linux-64/pkg.conda --json
```

Extract package contents for manual review:

```bash
python3 scripts/rattler_channel.py extract-package \
  --package-file output/linux-64/pkg.conda \
  --dest /tmp/pkg-inspect
```

Use inspection for license files, binary layout, prefix leakage, Python metadata, and unexpected vendored content.

## Generate and Maintain Recipes

Generate starter recipes:

```bash
python3 scripts/rattler_channel.py generate-recipe pypi jinja2
python3 scripts/rattler_channel.py generate-recipe cran dplyr
python3 scripts/rattler_channel.py generate-recipe cpan Try-Tiny
python3 scripts/rattler_channel.py generate-recipe luarocks luasocket
```

For ecosystem-specific flags, either pass raw arguments with the passthrough command or use `--extra-arg=<flag>`:

```bash
python3 scripts/rattler_channel.py rattler -- generate-recipe pypi --write jinja2
python3 scripts/rattler_channel.py generate-recipe pypi jinja2 --extra-arg=--write
```

Check for recipe updates without modifying files:

```bash
python3 scripts/rattler_channel.py bump-recipe --recipe path/to/recipe.yaml --check-only
```

Bump to an explicit version and update checksums:

```bash
python3 scripts/rattler_channel.py bump-recipe --recipe path/to/recipe.yaml --version 1.2.3
```

Review recipe diffs after every bump. Do not accept changed source URLs, build scripts, or dependency ranges blindly.

## Debug and Patch

Use native `rattler-build debug` commands through passthrough because debug state is interactive and context dependent:

```bash
python3 scripts/rattler_channel.py rattler -- debug setup --recipe path/to/recipe
python3 scripts/rattler_channel.py rattler -- debug shell
python3 scripts/rattler_channel.py rattler -- debug run
python3 scripts/rattler_channel.py rattler -- debug create-patch --help
```

Normal patch flow:

1. Run `debug setup` for the failing recipe.
2. Enter `debug shell` or modify files in the prepared work directory.
3. Re-run the build script with `debug run`.
4. Generate a unified patch with `debug create-patch`.
5. Store the patch next to the recipe and add it to `source.patches`.

Prefer recipe dependency/compiler/build-system fixes over patches. Patch upstream source only when the recipe cannot express the needed fix cleanly.

## Rebuild and Reproducibility

Rebuild from recipe metadata stored inside an existing package:

```bash
python3 scripts/rattler_channel.py rebuild --package-file output/linux-64/pkg.conda
```

Use this for reproducibility checks. For high assurance, compare the rebuilt package against the original with external tools such as `diffoscope` after extracting both packages.

## Publish, Upload, and Auth

Publishing is external-state-changing. Do not run it unless the user explicitly names the target channel and confirms credentials/environment are ready.

Useful native entry points:

```bash
python3 scripts/rattler_channel.py rattler -- auth login --help
python3 scripts/rattler_channel.py rattler -- upload --help
python3 scripts/rattler_channel.py rattler -- publish --help
```

`publish` can build recipes or accept existing `.conda` packages, upload to a target channel, and index the result:

```bash
rattler-build publish --to file:///tmp/local-channel output/linux-64/pkg.conda
rattler-build publish --to https://prefix.dev/my-channel path/to/recipe.yaml
```

Supported target families include prefix.dev, anaconda.org, Quetz, Artifactory, S3, and filesystem channels. Inspect and test packages before remote upload.

## CI, Completion, and TUI

For CI, prefer native `rattler-build` commands inside the workflow so the matrix, credentials, and artifacts are visible in CI configuration. Use render-only jobs for recipe validation and separate publish jobs gated by tags or manual approval.

Generate shell completions locally:

```bash
rattler-build completion --shell bash > rattler-build.bash
rattler-build completion --shell zsh > _rattler-build
```

The wrapper does not manage TUI or playground workflows. Use upstream rattler-build tooling directly when those surfaces are useful.
