# Monata Env Design

## Goal

Rename `monata-sim-env` to `monata-env` and narrow the skill to managing the
global circuit-tool runtime that Monata projects depend on.

The skill must not install Python, Monata, or Python packages. It must not
bootstrap Monata techlibs. Its live verification must test only circuit tools
in an isolated environment.

## Scope

`monata-env` owns:

- Detecting the circuit tools needed by the current Monata workspace.
- Building or reusing local conda packages for those tools when needed.
- Installing those tools into a pixi global environment named `monata-env`.
- Exposing the installed tool commands through pixi global shims.
- Verifying those commands directly with tool-level smoke tests.

`monata-env` does not own:

- Creating or modifying a project-local `pixi.toml`.
- Installing `python`, `monata`, or any Python package.
- Bootstrapping `MONATA_HOME` techlibs.
- Running demos that import `monata`.

## Runtime Design

The default tool set is `ngspice` and `openvaf-r`. The detector may reduce or
extend that set based on a workspace inspection, but it must not include Python
packages or Monata packages.

The default install command shape is:

```bash
pixi global install --environment monata-env \
  --channel "file://$CONDA_BUILD_OUTPUT_DIR" \
  --channel https://prefix.dev/conda-forge \
  --expose ngspice=ngspice \
  --expose openvaf-r=openvaf-r \
  ngspice openvaf-r
```

The local artifact channel stays explicit. If a requested circuit-tool package
is missing from the user-provided channel, the skill may build only the missing
required tool packages through the bundled `conda-build` helper. It must not
build the full recipe set or Xyce stack unless the user explicitly asks for
those tools.

## Verification Design

Static skill tests remain the default deterministic harness mode. They assert
the documented command boundaries and installation files without running live
package installs.

Live tests use a new explicit Singularity provider. The provider runs tests
with `/opt/singularity-ce/4.1.1/bin/singularity` when available, binds the repo
read-only or read-mostly into a temporary container workspace, and points all
mutable state at temporary directories:

```bash
HOME=/tmp/skill-home
PIXI_HOME=/tmp/skill-home/.pixi
XDG_CACHE_HOME=/tmp/skill-home/.cache
RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler
CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel
```

The provider is opt-in, so normal local validation does not download images,
write pixi global state, or modify the user's current environment. Temporary
directories are removed after each run unless `--keep-temp` is passed.

Live smoke tests must avoid importing `monata`. They verify only exposed
circuit-tool commands, starting with:

```bash
ngspice --version
openvaf-r --help
```

## Repository Changes

The plugin directory, skill directory, plugin manifests, marketplace entries,
OpenAI prompt metadata, README references, and harness cases all move from
`monata-sim-env` to `monata-env`.

The old techlib bootstrap and Monata README demo helper scripts are removed
from this plugin. Standalone techlib setup remains in the existing
`monata-techlib` plugin.

## Error Handling

If `pixi` is missing, the skill stops and asks the user to install pixi or
approve a specific install command. It does not install host tools silently.

If `rattler-build` is missing and missing circuit-tool packages must be built,
the skill asks before installing `rattler-build` globally.

If Singularity live testing is requested and Singularity is missing, the
harness fails with a clear message and leaves static tests available.
