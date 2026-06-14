# skills

Reusable agent skills maintained by lizhangmai.

These skills are small, composable instruction packs for coding agents. They
work as plain `SKILL.md` directories first, then expose thin installation
metadata for Claude Code, Codex, and other agents.

## Quickstart

### Claude Code

Add this repository as a Claude Code plugin marketplace:

```text
/plugin marketplace add https://github.com/lizhangmai/skills
/plugin install monata-sim-env@lizhangmai
/plugin install conda-build@lizhangmai
```

Then ask Claude Code:

```text
Use the monata-sim-env skill to set up a Monata simulation environment.

Use this final local conda channel for circuit-tool packages:
CONDA_BUILD_OUTPUT_DIR=<absolute-path-you-choose>
```

Replace `<absolute-path-you-choose>` with a real absolute path before sending
the prompt. The skill should ask for this value instead of choosing one when it
is missing.

### Cross-Agent Install

Use the open agent skills installer for Codex and other supported agents:

```bash
npx skills add lizhangmai/skills --skill monata-sim-env --skill conda-build
```

For Codex global install:

```bash
npx skills add lizhangmai/skills -g -a codex --skill monata-sim-env --skill conda-build -y
```

### Local Fallback

For agents without marketplace or `npx skills` support, use the repository
helper script:

```bash
python3 scripts/install.py --list
python3 scripts/install.py --target codex --skill monata-sim-env
python3 scripts/install.py --target codex --skill conda-build
```

Use symlinks during local skill development:

```bash
python3 scripts/install.py --target codex --skill monata-sim-env --mode symlink --force
```

## Skills

| Skill | Audience | Purpose |
| --- | --- | --- |
| `monata-sim-env` | Monata users | Set up a pixi environment that installs Monata from PyPI, builds or reuses local circuit-tool packages, and verifies `ngspice`. |
| `conda-build` | Package maintainers and advanced users | Manage local self-use conda channels with `rattler-build`, including build, test, inspect, render, debug, patch, bump, rebuild, and publish guidance. |

Maintainer-only release workflows should live outside this public skills
repository so generic skill installers do not expose them to ordinary users.

## Layout

```text
.claude-plugin/
  marketplace.json
skills/
  monata-sim-env/
    .claude-plugin/plugin.json
    SKILL.md
    agents/openai.yaml
  conda-build/
    .claude-plugin/plugin.json
    SKILL.md
    agents/openai.yaml
    assets/recipe-sets/
    scripts/
    references/
scripts/
  install.py
  validate.py
```

## Validate

Before publishing changes:

```bash
python3 scripts/validate.py
claude plugin validate .
claude plugin validate skills/monata-sim-env
claude plugin validate skills/conda-build
```

## Publishing Boundary

This repository should contain reusable skills, helper scripts, references, and
public recipes. It should not vendor third-party simulator source trees,
compiled EDA tools, private tokens, internal release credentials, or
machine-specific storage paths.
