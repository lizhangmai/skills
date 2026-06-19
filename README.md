# skills

Reusable agent skills and plugin adapters maintained by lizhangmai.

This repository publishes ordinary `SKILL.md` skills and the thin plugin
metadata needed by Codex and Claude Code. The runtime content lives under
`plugins/<plugin>/skills/<skill>/`; generic skills installers can discover the
same skills directly from the repository.

## Install

Use any one of these equivalent installation paths. For Monata circuit-tool
runtime setup, install only `monata-env`; it builds or reuses required
circuit-tool packages, installs them into a pixi global environment named
`monata-env`, exposes the tool commands, and runs direct tool smoke tests.
`conda-build` and `monata-techlib` remain available as lower-level standalone
tools for advanced use.

### Open Skills CLI

Use the Open Skills CLI for agents that support plain skills or do not have a
dedicated plugin marketplace:

```bash
npx skills@latest add lizhangmai/skills --skill monata-env
```

To inspect what the repository exposes before installing:

```bash
npx skills@latest add lizhangmai/skills --list
```

Pass `--agent <agent-name>` when you want to target a specific installed agent.

### Codex Plugin Marketplace

Add this repository as a Codex plugin marketplace:

```bash
codex plugin marketplace add https://github.com/lizhangmai/skills --ref main
codex plugin list --marketplace lizhangmai --available --json
codex plugin add monata-env@lizhangmai
```

After installing, start a new Codex thread in the target project directory and
ask Codex:

```text
Use the monata-env skill to set up global Monata circuit tools with pixi global.
CONDA_BUILD_OUTPUT_DIR=<absolute-path-you-choose>
```

Replace `<absolute-path-you-choose>` with a real absolute path before sending
the prompt. The skill inspects the Monata workspace before choosing tool
packages; the current Monata baseline is `ngspice` plus `openvaf-r`.

`monata-techlib` remains available as a lower-level standalone helper for
private/offline techlib collections:

```text
Use the monata-techlib skill directly to install local techlib resources.
MONATA_TECHLIB_SOURCE=<path-to-local-techlib-source>
MONATA_HOME=<absolute-monata-home>
```

Update the marketplace snapshot when this repository changes:

```bash
codex plugin marketplace upgrade lizhangmai
codex plugin remove monata-env@lizhangmai
codex plugin add monata-env@lizhangmai
```

### Claude Code Plugin Marketplace

Add this repository as a Claude Code plugin marketplace:

```text
/plugin marketplace add https://github.com/lizhangmai/skills
/plugin marketplace update lizhangmai
/plugin install monata-env@lizhangmai
/reload-plugins
```

Then ask Claude Code:

```text
Use the monata-env skill to set up global Monata circuit tools with pixi global.
CONDA_BUILD_OUTPUT_DIR=<absolute-path-you-choose>
```

### Repository Helper

For local development or offline testing of this repository, use the helper
script to install plain `SKILL.md` directories:

```bash
python scripts/install.py --list
python scripts/install.py --target codex --skill monata-env
python scripts/install.py --target codex --skill conda-build
python scripts/install.py --target codex --skill monata-techlib
```

Use symlinks during local skill development:

```bash
python scripts/install.py --target codex --skill monata-env --mode symlink --force
```

## Plugins

| Plugin | Audience | Purpose |
| --- | --- | --- |
| `monata-env` | Monata users | Global circuit-tool setup for Monata: inspect the workspace, build or reuse local circuit-tool packages, install them into pixi global `monata-env`, expose tool commands, and smoke-test `ngspice`/`openvaf-r`. |
| `conda-build` | Package maintainers and advanced users | Manage local self-use conda channels with `rattler-build`, including build, test, inspect, render, debug, patch, bump, rebuild, and publish guidance. |
| `monata-techlib` | Advanced Monata users | Standalone techlib resource setup when a user wants only model-library installation outside the full Monata environment workflow. |

Maintainer-only release workflows should live outside this public skills
repository so generic skill installers do not expose them to ordinary users.

## Layout

```text
.agents/
  plugins/
    marketplace.json       # Codex marketplace
.claude-plugin/
  marketplace.json         # Claude Code marketplace
plugins/
  monata-env/
    .codex-plugin/plugin.json
    .claude-plugin/plugin.json
    skills/monata-env/
      SKILL.md
      agents/openai.yaml
      scripts/
  conda-build/
    .codex-plugin/plugin.json
    .claude-plugin/plugin.json
    skills/conda-build/
      SKILL.md
      agents/openai.yaml
      assets/recipe-sets/
      scripts/
      references/
  monata-techlib/
    .codex-plugin/plugin.json
    .claude-plugin/plugin.json
    skills/monata-techlib/
      SKILL.md
      agents/openai.yaml
      scripts/
scripts/
  install.py
  validate.py
```

The Open Skills CLI discovers the nested `SKILL.md` directories, while Codex
and Claude Code use their plugin manifests at each plugin root.

## Validate

Before publishing changes:

```bash
npx skills@latest add . --list
python scripts/validate.py
python ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/monata-env
python ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/conda-build
python ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/monata-techlib
claude plugin validate .
claude plugin validate plugins/monata-env
claude plugin validate plugins/conda-build
claude plugin validate plugins/monata-techlib
```

Use any Python 3.10+ executable for the Codex plugin validator.

Run deterministic skill behavior scenarios locally:

```bash
python scripts/skill_harness.py list
python scripts/skill_harness.py run
python scripts/render_skill_feedback.py
```

The harness installs skills into temporary agent homes, uses fixtures under
`tests/fixtures/`, writes ignored reports under `reports/`, and checks
guardrails such as missing output directories, no silent global tool installs,
minimal Monata circuit-tool builds, pixi global isolation, and techlib
redistribution boundaries.

## Publishing Boundary

This repository should contain reusable skills, helper scripts, references, and
public recipes. It should not vendor third-party simulator source trees,
compiled EDA tools, private tokens, internal release credentials, or
machine-specific storage paths.
