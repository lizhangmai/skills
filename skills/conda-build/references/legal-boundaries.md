# Legal and Packaging Boundaries

## Default Position

Treat this skill as a local package-build assistant, not a redistribution mechanism. It may help the user render recipes, fetch upstream sources through rattler-build, build conda packages, and verify local package outputs. It should not publish compiled binaries or third-party source bundles unless the user explicitly asks for redistribution packaging and license review.

## Practical Rules

- Keep Monata-style Python packages limited to their own source code, metadata, and documentation.
- Keep third-party simulator recipes in this skill repository or a dedicated packaging repository, not inside the Monata Python wheel or source distribution.
- Do not copy ngspice, Xyce, OpenVAF, XDM, or other third-party source trees into this skill repository.
- Do not publish compiled simulator binaries from this skill unless the user has selected a redistribution strategy and reviewed every relevant license.
- When asked about legal risk, inspect the exact upstream license files fetched by the selected recipe and distinguish local package builds from redistribution.

## Agent Behavior

If the user asks to bundle, vendor, statically link, upload, or redistribute a simulator, stop the normal build flow and perform a license-focused review first. Report concrete license files and package contents; avoid broad legal conclusions without evidence.
