# Monata Env Isolated Testing

Use this reference for live checks that might touch pixi, package caches,
local channels, or Singularity state.

## Container Wrapper

Use `scripts/skill_container.py` with a disposable `--state-dir`. The wrapper
sets:

```text
HOME=/tmp/skill-home
PIXI_HOME=/tmp/skill-home/.pixi
XDG_CACHE_HOME=/tmp/skill-home/.cache
RATTLER_CACHE_DIR=/tmp/skill-home/.cache/rattler
CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel
SINGULARITY_CACHEDIR=<state-dir>/singularity-cache
SINGULARITY_TMPDIR=<state-dir>/singularity-tmp
```

Always run with `--dry-run` first and inspect binds, image, workspace, channel,
and command payload. Add `--require-command` for commands that must exist
inside the image.

## Test Image Tier

Review `plan.decisions` item `test_image` before expensive live checks.
Prefer `prepare_dedicated` when Singularity can build a local SIF. The helper
`scripts/prepare_monata_env_test_image.py` creates an image with python3, git,
and pixi, then validates those commands through the container wrapper.

Use `host_pixi_bind` only as a fallback when image build is unavailable. Use
`provided_image` when the user gives a prebuilt `.sif`. If fakeroot fails due
to missing `/etc/subuid` or `/etc/subgid`, ask for administrator setup, use a
configured remote builder with `--remote`, bind a host pixi executable, or ask
for a local image.

## Planner, Channel, Install Tiers

- Planner tier: requires `python3`; runs `plan_monata_env.py` in the container
  and writes an isolated manifest seed.
- Channel tier: requires `python3` plus the bound conda-build helper; runs
  `execute_monata_env_runbook.py --step check_channel` and records existing
  package artifacts.
- Install/smoke tier: requires pixi and enough runtime libraries for installed
  tools. Keep this tier separate until preflight proves `pixi` is available.

For a local smoke validation with trusted host pixi, pass `--host-pixi-root` to
the planner and run the generated `commands.install_smoke`. That command binds
only `<host-pixi-root>/bin/pixi` read-only, prepends
`/tmp/skill-home/.pixi/bin` and `/opt/host-pixi/bin`, and keeps `PIXI_HOME`
inside `/tmp/skill-home`.

When trusted local KLayout/Xschem source checkouts are provided, run
`commands.install_smoke_upstream`. It binds sources read-only under
`/mnt/sources/<package>` and includes the optional `upstream_installed_tests`
step after smoke.

## Failure Handling

If the image starts but lacks a required command, the wrapper returns
`missing-required-commands` and recommends
`choose-container-with-required-commands`. If pulling `docker://...` fails, it
can recommend `use-local-container-image`.

Use `bash -c`, not `bash -lc`, when relying on `--prepend-path`; login shells
may reset PATH and hide the bound pixi binary.
