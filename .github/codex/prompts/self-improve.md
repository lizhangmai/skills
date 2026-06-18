You are maintaining this skills repository. Make only the minimal tracked-file change needed to address the deterministic skill harness feedback in `reports/skill-feedback.md`.

Rules:
- Do not push, create pull requests, publish packages, authenticate to remote services, or modify branch protection. The workflow handles PR creation after verification.
- Do not add live Monata package builds, global installs, external publishing, or network-heavy tests.
- Prefer updating `SKILL.md`, harness cases, fixtures, or validation scripts only when that is the smallest correct fix.
- Preserve existing user changes and keep unrelated files untouched.
- After editing, run `python scripts/validate.py` and `python scripts/skill_harness.py run`.

Expected output:
- A minimal diff.
- Passing local validation.
- No changes under `reports/`.
