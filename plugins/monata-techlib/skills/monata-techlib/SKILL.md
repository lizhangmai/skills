---
name: monata-techlib
description: Bootstrap, install, and validate Monata technology-library resources under MONATA_HOME. Use when a user asks an agent to one-click configure Monata techlibs; download official PTM model cards and the VA-Models BSIM-CMG source subset; prepare PTM_MG or PTM_BULK resources; import a local monata-techlib checkout or extracted archive; place PTM, BSIM, PDK, SPICE model-card, or Verilog-A resource directories under ~/.monata/techlibs or a user-provided MONATA_HOME; preserve third-party notices; or verify that Monata TechlibRegistry can load installed techlibs.
---

# Monata Techlib

## Goal

One-click configure Monata technology libraries by downloading official public
model resources, generating Monata-compatible metadata, installing them into:

```text
$MONATA_HOME/techlibs
```

If `MONATA_HOME` is not explicitly set by the user or environment, use:

```text
~/.monata
```

After installation, verify that the target directory contains `techlib.toml`
entries and, when Monata is installed, that `TechlibRegistry` can load them.

## Rules

- Do not vendor, mirror, or redistribute third-party model cards inside this
  skill or its repository.
- Do not treat PTM, PDK, SPICE model-card, or Verilog-A resources as MIT
  licensed unless their own upstream license says so.
- Download PTM model cards only from the official public PTM page and its
  linked Google Drive files. Download the BSIM-CMG Verilog-A source subset only
  from the VA-Models GitHub repository. Do not use unofficial mirrors.
- Preserve root `LICENSE`, `NOTICE`, `TECHLIBS.toml`, `SHA256SUMS`, and
  per-techlib license/source metadata when installing a collection.
- Reject simulator binaries and generated model artifacts such as `ngspice`,
  `openvaf`, `xyce`, `.so`, `.dll`, `.dylib`, `.exe`, and `.osdi` files.
- Do not create a pixi environment, build conda packages, install ngspice, or
  compile OpenVAF/OSDI artifacts. Use `monata-env` for global circuit-tool
  setup and `conda-build` for package builds.
- Prefer copy mode for end users and symlink mode only for local development.
- If the user asks for a public redistributable techlib package, install only
  first-party metadata and instruct them to keep third-party model files as
  local user-provided resources unless redistribution rights are clear.

## Workflow

1. Determine `MONATA_HOME`:
   - Use an explicit user-provided path first.
   - Otherwise use the environment variable.
   - Otherwise use `~/.monata`.
2. Run the one-click PTM bootstrap unless the user explicitly asks for a local
   private/offline source:

   ```bash
   python scripts/install_monata_techlib.py bootstrap-ptm \
     --monata-home "<monata-home>"
   ```

   This downloads official PTM resources and the VA-Models BSIM-CMG source
   subset, caches downloads under `$MONATA_HOME/downloads/ptm-official`,
   generates `PTM_MG` and `PTM_BULK`, installs them under
   `$MONATA_HOME/techlibs`, preserves notices, and verifies the install.

   Use `--techlib PTM_MG` or `--techlib PTM_BULK` to install only one family.
   Reruns are idempotent: already installed techlibs are skipped unless
   `--force` is provided. If Google Drive or GitHub networking fails, rerun the
   same command; completed downloads are reused from the cache.

3. For a local private/offline source only, determine the source:
   - Use a path explicitly provided by the user first.
   - Otherwise check `MONATA_TECHLIB_SOURCE`.
   - Otherwise check whether the current directory or `./monata-techlib`
     contains `TECHLIBS.toml`, `techlibs/`, or a single `techlib.toml`.
   - If no source is available, ask for a local checkout, extracted archive, or
     directory containing model resources.

4. Install local private/offline techlibs:

   ```bash
   python scripts/install_monata_techlib.py install \
     --source "<source-dir>" \
     --monata-home "<monata-home>"
   ```

   Use `--techlib <name>` one or more times to install a subset. Use
   `--mode symlink` only for development checkouts. Use `--force` only when the
   user explicitly wants to replace existing installed techlibs.

5. Verify:

   ```bash
   python scripts/install_monata_techlib.py verify \
     --monata-home "<monata-home>"
   ```

6. Report the installed root and the environment line the user can reuse:

   ```bash
   export MONATA_HOME="<monata-home>"
   ```

## Accepted Source Shapes

Collection checkout or archive:

```text
TECHLIBS.toml
LICENSE
NOTICE
SHA256SUMS
techlibs/
  PTM_MG/
    techlib.toml
    models/
    model_sources/
  PTM_BULK/
    techlib.toml
    models/
```

Plain techlibs directory:

```text
techlibs/
  <techlib-name>/
    techlib.toml
```

Single techlib directory:

```text
<techlib-name>/
  techlib.toml
```

## Verification With Monata

If Monata is available in the active Python environment, verify discovery:

```bash
MONATA_HOME="<monata-home>" python - <<'PY'
from monata.techlib.registry import TechlibRegistry

registry = TechlibRegistry()
print(registry.list_techlibs())
PY
```

If Monata is not installed, report filesystem verification only and suggest
running `monata-env` first when the user also needs global circuit tools.

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
