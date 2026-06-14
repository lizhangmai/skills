# skills

Reusable agent skills and plugin adapters maintained by lizhangmai.

This repository publishes ordinary `SKILL.md` skills and the thin plugin
metadata needed by Codex and Claude Code. The runtime content lives under
`plugins/<plugin>/skills/<skill>/`; generic skills installers can discover the
same skills directly from the repository.

## Install

Use any one of these equivalent installation paths. For Monata simulation
workflows, install both `monata-sim-env` and `conda-build`.

### Open Skills CLI

Use the Open Skills CLI for agents that support plain skills or do not have a
dedicated plugin marketplace:

```bash
npx skills@latest add lizhangmai/skills --skill monata-sim-env --skill conda-build
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
codex plugin add monata-sim-env@lizhangmai
codex plugin add conda-build@lizhangmai
```

After installing, start a new Codex thread in the target project directory and
ask Codex:

```text
Use the monata-sim-env skill to set up this Monata environment.
CONDA_BUILD_OUTPUT_DIR=<absolute-path-you-choose>
```

Replace `<absolute-path-you-choose>` with a real absolute path before sending
the prompt. The skill inspects the Monata workspace before choosing tool
packages; the current Monata baseline is `ngspice` plus `openvaf-r`.

Update the marketplace snapshot when this repository changes:

```bash
codex plugin marketplace upgrade lizhangmai
codex plugin remove monata-sim-env@lizhangmai
codex plugin add monata-sim-env@lizhangmai
codex plugin remove conda-build@lizhangmai
codex plugin add conda-build@lizhangmai
```

### Claude Code Plugin Marketplace

Add this repository as a Claude Code plugin marketplace:

```text
/plugin marketplace add https://github.com/lizhangmai/skills
/plugin marketplace update lizhangmai
/plugin install monata-sim-env@lizhangmai
/plugin install conda-build@lizhangmai
/reload-plugins
```

Then ask Claude Code:

```text
Use the monata-sim-env skill to set up this Monata environment.
CONDA_BUILD_OUTPUT_DIR=<absolute-path-you-choose>
```

### Repository Helper

For local development or offline testing of this repository, use the helper
script to install plain `SKILL.md` directories:

```bash
python3 scripts/install.py --list
python3 scripts/install.py --target codex --skill monata-sim-env
python3 scripts/install.py --target codex --skill conda-build
```

Use symlinks during local skill development:

```bash
python3 scripts/install.py --target codex --skill monata-sim-env --mode symlink --force
```

## Plugins

| Plugin | Audience | Purpose |
| --- | --- | --- |
| `monata-sim-env` | Monata users | Inspect a Monata workspace, set up a pixi environment, build or reuse the needed local circuit-tool packages, and verify `ngspice` plus OpenVAF tooling. |
| `conda-build` | Package maintainers and advanced users | Manage local self-use conda channels with `rattler-build`, including build, test, inspect, render, debug, patch, bump, rebuild, and publish guidance. |

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
  monata-sim-env/
    .codex-plugin/plugin.json
    .claude-plugin/plugin.json
    skills/monata-sim-env/
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
python3 scripts/validate.py
python3.10 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/monata-sim-env
python3.10 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/conda-build
claude plugin validate .
claude plugin validate plugins/monata-sim-env
claude plugin validate plugins/conda-build
```

Use any Python 3.10+ executable for the Codex plugin validator.

## Publishing Boundary

This repository should contain reusable skills, helper scripts, references, and
public recipes. It should not vendor third-party simulator source trees,
compiled EDA tools, private tokens, internal release credentials, or
machine-specific storage paths.
