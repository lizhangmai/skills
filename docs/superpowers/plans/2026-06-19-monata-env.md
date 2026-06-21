# Monata Env Implementation Plan

> Historical note: this completed plan records the rename from
> `monata-sim-env` to `monata-env`. The current implementation and executable
> guidance live in `plugins/monata-env/skills/monata-env/SKILL.md`; do not use
> this historical plan as the active install runbook.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Rename `monata-sim-env` to `monata-env` and make it manage only global Monata circuit-tool dependencies through pixi global.

**Architecture:** The plugin keeps the existing repository conventions: plugin folder, skill folder, manifest names, marketplace entries, README references, and harness case names all match `monata-env`. Static harness cases prove command boundaries. A new explicit Singularity harness provider wraps selected scenario runs in a temporary container context and redirects all mutable state to temp paths.

**Tech Stack:** Python 3 standard library, repository YAML/JSON harness cases, pixi global command documentation, Singularity CE 4.1.1 for opt-in live isolation.

---

### Task 1: Add Failing Static Cases For New Skill Contract

**Files:**
- Create: `tests/cases/monata-env-global-tools.yaml`
- Create: `tests/cases/monata-env-no-monata-or-techlibs.yaml`

- [x] **Step 1: Write failing global-tool case**

Create `tests/cases/monata-env-global-tools.yaml`:

```json
{
  "name": "monata-env-global-tools",
  "skill": "monata-env",
  "provider": "static",
  "workspace_fixture": "monata-basic",
  "prompt": "Use the monata-env skill to set up global Monata circuit tools. CONDA_BUILD_OUTPUT_DIR=/tmp/monata-channel",
  "env": {
    "CONDA_BUILD_OUTPUT_DIR": "/tmp/monata-channel"
  },
  "fake_bins": {
    "pixi": {"stdout": "pixi 0.0.0-test"},
    "git": {"stdout": "git version 0.0.0-test"},
    "rattler-build": {"stdout": "rattler-build 0.0.0-test"}
  },
  "assertions": {
    "skill_must_contain": [
      "pixi global install --environment monata-env",
      "--channel \"file://$CONDA_BUILD_OUTPUT_DIR\"",
      "--channel https://prefix.dev/conda-forge",
      "--expose ngspice=ngspice",
      "--expose openvaf-r=openvaf-r",
      "ngspice --version",
      "openvaf-r --help"
    ],
    "installed_files": [
      "SKILL.md",
      "scripts/detect_monata_tools.py"
    ]
  }
}
```

- [x] **Step 2: Write failing no-Monata/no-techlib case**

Create `tests/cases/monata-env-no-monata-or-techlibs.yaml`:

```json
{
  "name": "monata-env-no-monata-or-techlibs",
  "skill": "monata-env",
  "provider": "static",
  "workspace_fixture": "monata-basic",
  "prompt": "Use the monata-env skill to install only global circuit and layout tools. CONDA_BUILD_OUTPUT_DIR=/tmp/monata-channel",
  "assertions": {
    "skill_must_contain": [
      "Do not install Monata",
      "Do not install the `monata` Python package",
      "Do not bootstrap Monata techlibs",
      "Do not create or modify a project-local pixi.toml"
    ],
    "skill_must_not_contain": [
      "pixi init",
      "pixi add",
      "monata>=0.1.1",
      "bootstrap_monata_techlibs.py",
      "write_monata_readme_demo.py",
      "TechlibRegistry",
      "pixi run python"
    ],
    "forbidden_commands": [
      "pixi init",
      "pixi add",
      "pixi run python"
    ]
  }
}
```

- [x] **Step 3: Run cases to verify RED**

Run:

```bash
python scripts/skill_harness.py run monata-env-global-tools monata-env-no-monata-or-techlibs
```

Expected: fails with `Unknown skill or missing SKILL.md: monata-env`.

### Task 2: Rename Plugin And Update Skill Contract

**Files:**
- Move: `plugins/monata-sim-env/` to `plugins/monata-env/`
- Delete: `plugins/monata-env/skills/monata-env/scripts/bootstrap_monata_techlibs.py`
- Delete: `plugins/monata-env/skills/monata-env/scripts/write_monata_readme_demo.py`
- Modify: `plugins/monata-env/.codex-plugin/plugin.json`
- Modify: `plugins/monata-env/.claude-plugin/plugin.json`
- Modify: `plugins/monata-env/skills/monata-env/SKILL.md`
- Modify: `plugins/monata-env/skills/monata-env/agents/openai.yaml`
- Modify: `.agents/plugins/marketplace.json`
- Modify: `.claude-plugin/marketplace.json`
- Modify: `README.md`
- Modify: `plugins/conda-build/skills/conda-build/SKILL.md`
- Modify: `plugins/monata-techlib/skills/monata-techlib/SKILL.md`

- [x] **Step 1: Move directories**

Run:

```bash
git mv plugins/monata-sim-env plugins/monata-env
git mv plugins/monata-env/skills/monata-sim-env plugins/monata-env/skills/monata-env
git rm plugins/monata-env/skills/monata-env/scripts/bootstrap_monata_techlibs.py
git rm plugins/monata-env/skills/monata-env/scripts/write_monata_readme_demo.py
```

- [x] **Step 2: Update manifests and marketplace references**

Replace plugin names, skill paths, display names, descriptions, and default
prompts so they refer to `monata-env`, global pixi tools, and no Python or
techlib setup.

- [x] **Step 3: Rewrite `SKILL.md`**

The new `SKILL.md` must contain:

```markdown
---
name: monata-env
description: Set up and validate global circuit-tool dependencies for Monata projects with pixi global. Use when a user asks an agent to install or configure Monata circuit tools; inspect a Monata repository to choose required simulator packages; build or reuse ngspice and OpenVAF/OSDI packages; install them into a pixi global environment named monata-env; expose tool commands; or validate ngspice and openvaf-r without installing Monata or techlibs.
---
```

It must document:

```bash
pixi global install --environment monata-env \
  --channel "file://$CONDA_BUILD_OUTPUT_DIR" \
  --channel https://prefix.dev/conda-forge \
  --expose ngspice=ngspice \
  --expose openvaf-r=openvaf-r \
  ngspice openvaf-r
```

and verification:

```bash
ngspice --version
openvaf-r --help
```

- [x] **Step 4: Run RED cases to verify GREEN**

Run:

```bash
python scripts/skill_harness.py run monata-env-global-tools monata-env-no-monata-or-techlibs
```

Expected: both cases pass.

### Task 3: Migrate Existing Harness Cases

**Files:**
- Rename: `tests/cases/monata-sim-env-*.yaml` to `tests/cases/monata-env-*.yaml`
- Modify: migrated case JSON payloads

- [x] **Step 1: Rename and edit old cases**

Move existing cases to `monata-env-*`, set `"skill": "monata-env"`, update
prompts to use `monata-env`, and replace project-pixi expectations with global
pixi expectations.

- [x] **Step 2: Run all static harness cases**

Run:

```bash
python scripts/skill_harness.py run
```

Expected: all cases pass.

### Task 4: Add Singularity Provider Tests

**Files:**
- Modify: `scripts/skill_harness.py`
- Create: `tests/cases/monata-env-singularity-isolation.yaml`

- [x] **Step 1: Write failing case**

Create `tests/cases/monata-env-singularity-isolation.yaml`:

```json
{
  "name": "monata-env-singularity-isolation",
  "skill": "monata-env",
  "provider": "singularity-dry-run",
  "workspace_fixture": "monata-basic",
  "prompt": "Use the monata-env skill in an isolated Singularity test context. CONDA_BUILD_OUTPUT_DIR=/tmp/monata-channel",
  "assertions": {
    "must_contain": [
      "singularity",
      "--cleanenv",
      "--containall",
      "PIXI_HOME=/tmp/skill-home/.pixi",
      "CONDA_BUILD_OUTPUT_DIR=/tmp/skill-channel"
    ]
  }
}
```

- [x] **Step 2: Run case to verify RED**

Run:

```bash
python scripts/skill_harness.py run monata-env-singularity-isolation
```

Expected: fails because `singularity-dry-run` is currently gated by
`run_live_provider`.

- [x] **Step 3: Implement provider**

Add `build_singularity_command(case, temp_root, workspace, env)` returning a
command preview. Add provider handling:

- `singularity-dry-run`: does not execute Singularity; returns the preview in
  `details` so static assertions can validate the command boundary.
- `singularity`: checks `/opt/singularity-ce/4.1.1/bin/singularity`, creates
  temp home/cache/channel paths, and executes the selected case command inside
  a container when the case provides an image and command.

Use `--cleanenv`, `--containall`, `--home`, and explicit env assignments so
pixi state does not use the user's real home.

- [x] **Step 4: Run case to verify GREEN**

Run:

```bash
python scripts/skill_harness.py run monata-env-singularity-isolation
```

Expected: case passes.

### Task 5: Validate Repository

**Files:**
- No new files

- [x] **Step 1: Run structure validation**

Run:

```bash
python scripts/validate.py
```

Expected: `Validated 3 plugin(s).`

- [x] **Step 2: Run plugin validation**

Run:

```bash
python /home/S/lizhangmai/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/monata-env
python /home/S/lizhangmai/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/conda-build
python /home/S/lizhangmai/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/monata-techlib
```

Expected: all pass.

- [x] **Step 3: Run all harness cases**

Run:

```bash
python scripts/skill_harness.py run
```

Expected: all cases pass.

- [x] **Step 4: Check git state**

Run:

```bash
git status --short --branch
git diff --stat
```

Expected: only intended files changed.
