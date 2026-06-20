---
name: monata-env
description: Set up and validate global circuit-tool dependencies for Monata projects with pixi global. Use when a user asks an agent to install or configure Monata circuit tools; inspect a Monata repository to choose required simulator, schematic, and layout packages; build or reuse ngspice, OpenVAF/OSDI, KLayout, and Xschem packages; install them into a pixi global environment named monata-env; expose tool commands; or validate ngspice, openvaf-r, klayout, and xschem without installing Monata or techlibs.
---

# Monata Env

## Goal

Create or update a pixi global environment named `monata-env` that exposes the
circuit tools used by Monata projects. The default tool set is `ngspice`,
`openvaf-r`, `klayout`, and `xschem`.

This is an AI-native setup skill: inspect first, produce a small explicit plan,
ask for user confirmation only when the plan touches global state or needs a
fallback choice, execute deterministic helper commands, verify tools directly,
and leave a manifest of what was installed.

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
- Start with `scripts/plan_monata_env.py` for nontrivial setup requests. Treat
  its JSON as the session plan: detected packages, channel reuse, local-source
  status, recommended commands, test profiles, user-confirmation questions, and
  manifest path.
- Build KLayout from the public upstream source
  `https://github.com/KLayout/klayout/tree/v0.30.9` through the bundled
  `klayout` recipe. Keep the recipe source remote, pinned to the `v0.30.9`
  commit, and checksum-verified by default.
- Build Xschem from the public upstream source
  `https://codeberg.org/stef_xschem/xschem/src/tag/3.4.7` through the bundled
  `xschem` recipe. Keep the recipe source remote, pinned to the `3.4.7`
  commit, and checksum-verified by default.
- If the user explicitly provides a local source checkout for KLayout or
  Xschem, pass it to the conda-build helper with `--local-source`. The helper
  must create a temporary `source.path` overlay recipe and still use
  `rattler-build build --output-dir`; do not hand-copy `.conda` files into the
  channel and do not require `conda index`. Treat local source as trusted user
  input and confirm it is checked out to the requested upstream version
  (`v0.30.9` for KLayout, `3.4.7` for Xschem) before building. Pass
  `--local-source-ref package=ref` so the helper enforces this check.
- If the user-provided channel already contains the detected packages, skip the
  build and do not require `rattler-build`.
- If a container or minimal host image does not include `git`, local source ref
  validation must report `git-unavailable` and ask for a corrected validation
  path, a container with git, or user approval to proceed with trusted local
  sources for non-build upstream-installed tests. Do not crash on missing git.
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

4. Generate an AI-native setup plan before mutating global state:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --write-manifest \
     --format json
   ```

   If the user provided local upstream checkouts, add one argument per source:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --local-source klayout="$(realpath ../circuit/klayout)" \
     --local-source xschem="$(realpath ../circuit/xschem)" \
     --write-manifest \
     --format json
   ```

   The planner defaults optional upstream-installed checks to the `basic`
   profile. If the user explicitly accepts longer runtime and extra
   dependency/display risk, request the full upstream profile in the plan:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --local-source klayout="$(realpath ../circuit/klayout)" \
     --local-source xschem="$(realpath ../circuit/xschem)" \
     --upstream-profile full \
     --write-manifest \
     --format json
   ```

   If network access to container registries is unreliable and the user has a
   local Singularity image for live validation, pass it into the planner so the
   generated test-isolation decision uses that `.sif`:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --container-image /path/to/monata-env-python-3.12-slim.sif \
     --write-manifest \
     --format json
   ```

   For repeatable live install/upstream checks that should not depend on host
   tool shims, let the planner generate a dedicated test-image preparation
   command. The image must contain `python3`, `git`, and `pixi`; if a trusted
   local pixi binary is available, pass `--host-pixi-root` so the generated
   image definition can copy only `<host-pixi-root>/bin/pixi` into the image:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --session-dir /tmp/monata-env-session \
     --test-image-output /tmp/monata-env-session/monata-env-test.sif \
     --host-pixi-root /path/to/host-pixi-root \
     --write-manifest \
     --format json
   ```

   Run `plan.container.test_image.prepare_command` to write/build the image,
   then run `plan.container.test_image.validate_command` before using it as
   `--container-image`. If local Singularity build fails with a fakeroot or
   `/etc/subuid` mapping error, either ask an administrator to enable fakeroot,
   run `plan.container.test_image.remote_prepare_command` when a remote builder
   is configured, ask the user for a prebuilt `.sif`, or continue with the
   `host_pixi_bind` fallback.

   For live validation that should inspect the final package channel without
   overwriting the final install manifest, keep `--output-dir` pointed at the
   package channel and send transient logs/manifests to `--session-dir`:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --session-dir /tmp/monata-env-session \
     --write-manifest \
     --format json
   ```

   When `--session-dir` is supplied, the planner's generated Singularity
   commands keep container HOME, pixi, rattler, and image cache state under
   `<session-dir>/container-state`. Override that location only when you need a
   different disposable state root:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --session-dir /tmp/monata-env-session \
     --container-state-dir /tmp/monata-env-container-state \
     --write-manifest \
     --format json
   ```

   For an isolated live install/smoke check that reuses a trusted host pixi
   binary without mutating the host pixi global state, pass the pixi install
   root explicitly. The planner will include a ready-to-run
   `plan.decisions[*].options[*].commands.install_smoke` command that binds
   only `<host-pixi-root>/bin/pixi` read-only, puts the isolated
   `/tmp/skill-home/.pixi/bin` first on `PATH`, and keeps `PIXI_HOME` under
   `/tmp/skill-home`:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --session-dir /tmp/monata-env-session \
     --container-image /path/to/monata-env-python-3.12-slim.sif \
     --host-pixi-root /path/to/host-pixi-root \
     --write-manifest \
     --format json
   ```

   That generated command first runs the planner inside the container with
   `--write-manifest`, stores the planner JSON under
   `/tmp/skill-home/monata-env-session`, and then executes only the
   `install` and `smoke` runbook steps against that isolated manifest.
   When local KLayout/Xschem sources are also provided, the planner additionally
   emits `commands.install_smoke_upstream`; that command binds each source
   read-only under `/mnt/sources/<package>`, regenerates the manifest with
   container-local `--local-source` paths, and runs `install`, `smoke`, and
   `upstream_installed_tests` with the requested upstream profile.

   Review `plan.decisions` with the user when there is meaningful choice:
   source policy, pixi global writes, test isolation, and upstream test
   profile. Treat `plan.runbook` as the authoritative execution sequence. Each
   runbook item contains the command to run, whether user confirmation is
   required, which previous step ids it `depends_on`, where step
   `stdout_path` and `stderr_path` logs should be captured, and a
   `status_path` JSON file that the executor updates before and after the
   command. The `record_after` command must run after the step so the manifest
   keeps return codes, log file paths, package artifacts, and verification
   payloads.
   Each mutating or long-running runbook step has `timeout_seconds`; if a step
   appears to hang, inspect its `status_path` first to confirm whether the
   executor is still running the command. If a step times out, inspect the
   persisted stdout/stderr logs and use the executor's `next_actions` before
   retrying with a larger timeout or a local cache.
   Review the plan's `questions`. Ask the user before doing a
   recommended fallback such as creating temporary detached worktrees,
   installing missing host tools, or writing to the pixi global environment.
   Check `plan.helper.conda_build_script`: when it exists, the generated
   check/build commands already point at that helper path; when it is missing,
   resolve the helper checkout before executing check/build steps.
   For isolated live validation from this repository, the generated
   `test_isolation` command binds the full skills repo with `--repo-root` and
   passes `--conda-build-helper /mnt/skills/plugins/conda-build/...` into the
   container planner. This lets the container execute the planner and
   `check_channel` runbook step without cloning the helper or touching the
   user's host caches.

   Prefer the executor for runbook steps instead of manually retyping commands:

   ```bash
   python scripts/execute_monata_env_runbook.py \
     --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
     --format json
   ```

   By default this runs only recommended steps that do not require
   confirmation and skips downstream steps whose `depends_on` prerequisites
   were skipped or failed. After the user approves mutating steps such as build
   or pixi global install, run the selected steps explicitly:

   ```bash
   python scripts/execute_monata_env_runbook.py \
     --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
     --step build \
     --step install \
     --allow-confirmation-required \
     --format json
   ```

   If the executor returns `next_actions`, do not blindly retry. Use those
   structured suggestions to negotiate the next step with the user, such as
   providing local KLayout/Xschem source checkouts after network failure,
   refreshing the conda-build helper, creating a detached source worktree at
   the required tag, or inspecting missing exposed tool commands after smoke
   failure.

5. Detect the required circuit-tool packages from the Monata workspace when you
   need a shell list outside the planner:

   ```bash
   python scripts/detect_monata_tools.py --root "<project-workspace>" --format shell
   ```

   Run this from the installed or cloned `monata-env` skill directory. If a
   Monata workspace cannot be inspected, use the current baseline package set:
   `ngspice openvaf-r klayout xschem`.

6. Resolve the conda-build helper. Prefer a local sibling checkout:

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

   You can also pass an explicit helper path to the planner:

   ```bash
   python scripts/plan_monata_env.py \
     --root "<project-workspace>" \
     --output-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --conda-build-helper "$HOME/.cache/monata-env/skills/plugins/conda-build/skills/conda-build/scripts/rattler_channel.py" \
     --write-manifest \
     --format json
   ```

7. Check the user-provided channel. If all detected packages are present, skip
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

8. If any detected package is missing, build only missing work from the
   `circuit-toolchain` recipe set and let existing artifacts be reused. When
   the user gave local source directories, resolve them to absolute paths and
   pass one `--local-source package=path` argument per local checkout:

   ```bash
   KLAYOUT_SOURCE="$(realpath ../circuit/klayout)"
   XSCHEM_SOURCE="$(realpath ../circuit/xschem)"
   python scripts/rattler_channel.py build \
     --recipe-set circuit-toolchain \
     --package ngspice \
     --package openvaf-r \
     --package klayout \
     --package xschem \
     --local-source klayout="$KLAYOUT_SOURCE" \
     --local-source-ref klayout=v0.30.9 \
     --local-source xschem="$XSCHEM_SOURCE" \
     --local-source-ref xschem=3.4.7 \
     --skip-existing
   ```

   Omit `--local-source klayout=...` and `--local-source xschem=...` when the
   user did not provide local source checkouts; the bundled recipes then fetch
   pinned public sources from the network.

   If a provided checkout is not currently at the recipe version, do not change
   the user's checkout in place. Create a temporary detached worktree at the
   target tag and pass that worktree path:

   ```bash
   git -C ../circuit/klayout worktree add --detach /tmp/monata-sources/klayout-v0.30.9 v0.30.9
   git -C ../circuit/xschem worktree add --detach /tmp/monata-sources/xschem-3.4.7 3.4.7
   ```

   If `rattler-build` is missing but `pixi` is available, ask before installing
   it globally:

   ```bash
   pixi global install --channel https://prefix.dev/conda-forge rattler-build
   rattler-build --version
   ```

9. Install the detected circuit tools into the pixi global environment named
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

10. Verify the exposed circuit tools directly. Do not import `monata`:

   ```bash
   SMOKE_JSON="$CONDA_BUILD_OUTPUT_DIR/monata-env-smoke.json"
   SMOKE_ERR="$CONDA_BUILD_OUTPUT_DIR/monata-env-smoke.err"
   if python scripts/smoke_monata_env_tools.py --format json > "$SMOKE_JSON" 2> "$SMOKE_ERR"; then
     SMOKE_RC=0
   else
     SMOKE_RC=$?
   fi
   python scripts/record_monata_env_session.py \
     --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
     --command-kind smoke \
     --command "python scripts/smoke_monata_env_tools.py --format json" \
     --returncode "$SMOKE_RC" \
     --stdout-file "$SMOKE_JSON" \
     --stderr-file "$SMOKE_ERR" \
     --verification smoke="$SMOKE_JSON"
   test "$SMOKE_RC" -eq 0
   ```

   This minimal smoke test runs `ngspice`, compiles small OSDI models with
   `openvaf-r`, writes a GDS in KLayout batch mode, and checks `xschem --version`.

11. If the plan recommends `test_profiles.upstream_installed` and the user
   provided trusted local upstream checkouts, ask before running the optional
   upstream-installed profile:

   ```bash
   UPSTREAM_JSON="$CONDA_BUILD_OUTPUT_DIR/monata-env-upstream-installed.json"
   if python scripts/test_monata_env_upstream.py \
       --format json \
       --profile basic \
       --klayout-source "$(realpath ../circuit/klayout)" \
       --xschem-source "$(realpath ../circuit/xschem)" > "$UPSTREAM_JSON"; then
     UPSTREAM_RC=0
   else
     UPSTREAM_RC=$?
   fi
   python scripts/record_monata_env_session.py \
     --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
     --command-kind upstream_installed_tests \
     --command "python scripts/test_monata_env_upstream.py --format json --profile basic ..." \
     --returncode "$UPSTREAM_RC" \
     --stdout-file "$UPSTREAM_JSON" \
     --verification upstream_installed="$UPSTREAM_JSON"
   test "$UPSTREAM_RC" -eq 0
   ```

   This profile uses upstream test assets but calls the installed tools. The
   basic profile runs a small KLayout upstream script/Python-binding subset and
   an Xschem upstream `create_save` test from a temporary copy of the source
   test tree. Use `--profile full` only when the user accepts longer runtime
   and higher dependency/display risk. The full Xschem profile first records
   `xschem-basic-create-save`, then runs `xschem-full-regression`, so a timeout
   can still show whether basic installed-tool behavior passed. Full Xschem
   regression needs `tclsh`; the upstream test helper first looks inside the
   pixi global env prefix, then falls back to `PATH`. The executor will suggest
   installing/exposing Tcl, inspecting full-regression timeout output, rerunning
   the upstream helper with a larger `--timeout`, or re-planning with
   `--upstream-profile basic` when those cases occur.
   Planner-generated upstream commands use
   `--work-dir <session-dir>/monata-env-upstream-work --keep-work-dir` so the
   copied upstream test tree remains available after failures.

12. Prefer `scripts/execute_monata_env_runbook.py` so `runbook[*].record_after`
   runs automatically after build, install, smoke, and upstream test commands.
   If you must execute a command outside the planner output, call
   `scripts/record_monata_env_session.py` directly. The manifest must keep the
   plan JSON, exact commands run, package artifacts, local-source refs, pixi
   global environment name, per-step `stdout_file` and `stderr_file` logs,
   `verification.smoke`, and
   `verification.upstream_installed` when run.

   The `check_channel` step records artifacts already present in the local
   channel. This matters when all packages already exist and build is skipped;
   the manifest still needs package artifact evidence for the install.

   After a build command, record generated artifacts without requiring
   `conda index`:

   ```bash
   python scripts/record_monata_env_session.py \
     --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
     --command-kind build \
     --command "python scripts/rattler_channel.py build --recipe-set circuit-toolchain ..." \
     --returncode "$BUILD_RC" \
     --stdout-file "$CONDA_BUILD_OUTPUT_DIR/monata-env-build.out" \
     --stderr-file "$CONDA_BUILD_OUTPUT_DIR/monata-env-build.err" \
     --artifact-dir "$CONDA_BUILD_OUTPUT_DIR" \
     --package ngspice \
     --package openvaf-r \
     --package klayout \
     --package xschem
   ```

   After the pixi global install, record the exact install command and return
   code. If a step fails, still record its command and return code before
   diagnosing or asking the user for a fallback such as a local source checkout.

## Existing Circuit-Tool Environment

If the detected circuit tools are already available on `PATH`, still verify
the commands directly and report that no pixi global install was needed:

```bash
SMOKE_JSON="$CONDA_BUILD_OUTPUT_DIR/monata-env-smoke.json"
SMOKE_ERR="$CONDA_BUILD_OUTPUT_DIR/monata-env-smoke.err"
if python scripts/smoke_monata_env_tools.py --format json > "$SMOKE_JSON" 2> "$SMOKE_ERR"; then
  SMOKE_RC=0
else
  SMOKE_RC=$?
fi
python scripts/record_monata_env_session.py \
  --manifest "$CONDA_BUILD_OUTPUT_DIR/monata-env-install-manifest.json" \
  --command-kind smoke \
  --command "python scripts/smoke_monata_env_tools.py --format json" \
  --returncode "$SMOKE_RC" \
  --stdout-file "$SMOKE_JSON" \
  --stderr-file "$SMOKE_ERR" \
  --verification smoke="$SMOKE_JSON"
test "$SMOKE_RC" -eq 0
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

Use the skill-local container wrapper for live setup checks:

```bash
python scripts/skill_container.py \
  --state-dir /tmp/monata-env-skill-test \
  --workspace "<project-workspace>" \
  --image docker://python:3.12-slim \
  --require-command python3 \
  --dry-run \
  -- \
  bash -lc 'cd /mnt/project && python3 /mnt/skills/scripts/plan_monata_env.py --root /mnt/project --output-dir /tmp/skill-channel --session-dir /tmp/skill-home/monata-env-session --write-manifest --format json'
```

Remove `--dry-run` only when the printed command shows the expected binds and
temporary state directories. Add one `--require-command` per tool that must
exist inside the container before the command starts. If the container is
missing one, the wrapper returns `missing-required-commands` JSON instead of a
bare shell failure and recommends `choose-container-with-required-commands`.
Use `docker://python:3.12-slim` or another image with `python3` for planner
live checks; the previous bare Ubuntu image is useful only for isolation
preflight because it does not include Python by default.
If pulling or resolving `docker://...` fails because of network or registry
access, read `next_actions`; the wrapper can recommend
`use-local-container-image` so the user can provide a local `.sif` image or a
reachable mirror. For live install/smoke checks, keep
`CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel`; pixi global state is isolated by
`PIXI_HOME=/tmp/skill-home/.pixi`. The wrapper also sets host-side
`SINGULARITY_CACHEDIR` and `SINGULARITY_TMPDIR` under the selected state
directory so pulling a container image does not use the user's default
Singularity cache.

The expected isolation variables are:

```bash
HOME=/tmp/skill-home
PIXI_HOME=/tmp/skill-home/.pixi
XDG_CACHE_HOME=/tmp/skill-home/.cache
RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler
CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel
SINGULARITY_CACHEDIR=<state-dir>/singularity-cache
SINGULARITY_TMPDIR=<state-dir>/singularity-tmp
```

Use live checks in tiers:

- Test-image tier: review `plan.decisions` item `test_image` before expensive
  live checks. Prefer `prepare_dedicated` when Singularity can build a local SIF;
  it uses `scripts/prepare_monata_env_test_image.py` to create an image with
  python3, git, and pixi, then validates those commands with the container
  wrapper. Use `host_pixi_bind` only as a fallback when image build is not
  available; use `provided_image` when the user gives a prebuilt `.sif`. When
  the local machine lacks fakeroot subuid/subgid mappings, use the helper's
  `--remote` option only if a Singularity remote builder is already configured.

- Planner tier: requires `python3`; runs `plan_monata_env.py` in the container
  and writes the manifest seed.
- Channel tier: requires `python3` plus the bound `conda-build` helper; runs
  `execute_monata_env_runbook.py --step check_channel` in the container and
  records existing local-channel artifacts. Use `--session-dir` under
  `/tmp/skill-home` so this does not overwrite the final install manifest in
  the package channel.
- Install/smoke tier: requires a container image with `pixi` and enough runtime
  libraries for the tools. Keep this tier separate from planner/channel checks
  until the selected image passes `--require-command pixi`. For a local smoke
  validation where a trusted host pixi binary is already available, pass
  `--host-pixi-root` to `plan_monata_env.py` and run the generated
  `test_isolation` option's `commands.install_smoke`. That command binds only
  the host pixi executable read-only, puts the isolated pixi global bin first
  on `PATH`, and keeps `PIXI_HOME` in `/tmp/skill-home`:

  ```bash
  python scripts/skill_container.py \
    --state-dir /tmp/monata-env-install-test \
    --repo-root "<skills-repo>" \
    --workspace "<project-workspace>" \
    --channel "$CONDA_BUILD_OUTPUT_DIR" \
    --image /path/to/monata-env-python-3.12-slim.sif \
    --bind "<host-pixi-root>/bin/pixi:/opt/host-pixi/bin/pixi:ro" \
    --prepend-path /tmp/skill-home/.pixi/bin \
    --prepend-path /opt/host-pixi/bin \
    --require-command /usr/local/bin/python3 \
    --require-command pixi \
    -- \
    bash -c 'cd /mnt/project && mkdir -p /tmp/skill-home/monata-env-session && /usr/local/bin/python3 /mnt/skills/plugins/monata-env/skills/monata-env/scripts/plan_monata_env.py --root /mnt/project --output-dir /tmp/skill-channel --session-dir /tmp/skill-home/monata-env-session --conda-build-helper /mnt/skills/plugins/conda-build/skills/conda-build/scripts/rattler_channel.py --write-manifest --format json > /tmp/skill-home/monata-env-session/plan.json && /usr/local/bin/python3 /mnt/skills/plugins/monata-env/skills/monata-env/scripts/execute_monata_env_runbook.py --manifest /tmp/skill-home/monata-env-session/monata-env-install-manifest.json --step install --step smoke --allow-confirmation-required --format json'
  ```

  Use `bash -c`, not `bash -lc`, when relying on a prepended PATH; login shells
  may reset PATH and hide the bound pixi binary.
  When trusted local KLayout/Xschem source checkouts are provided, use the
  generated `commands.install_smoke_upstream` variant instead. It adds read-only
  source binds like
  `<klayout-source>:/mnt/sources/klayout:ro` and runs the optional
  `upstream_installed_tests` step after the smoke test.

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
