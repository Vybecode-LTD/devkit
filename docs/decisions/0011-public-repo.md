# 0011: The GitHub repo is public, for now

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** Decision 0008 called for a private repo. GitHub Actions minutes are free for public repos, and the owner would rather not pay for CI while DevKit is being built.
- **Decision:**
  - `Vybecode-LTD/devkit` is public. Being public doesn't make the code open source: `LICENSE` keeps every right, and third-party material is listed in `NOTICE`.
  - Commits use the owner's GitHub no-reply address. Before the first push, the history was rewritten to swap out the personal address and to remove the inventory.
  - What maps the owner's other projects stays out of git, in `docs/private/` (gitignored). That covers the inventory of `C:\DEV` and the name of the client folder. A copy of the inventory lives in the claude.ai Project.
- **Alternatives:** A private repo on a paid plan (the original 0008); self-hosted runners.
- **Consequences:** Anything committed is world-readable, so secrets, client material and private notes must never land. gitleaks runs in CI on every pull request, every push to `main` and once a week (decision 0015). The brand check can't run in CI, since it lives in the owner's VybeSite folder, so it runs locally before every PR that lifts code. Since 2026-11-13 a ruleset requires "CI result" on every commit pushed to `main` and blocks force pushes. That day `main` was rewritten once, before the ruleset, to take the API token's address off two early commits. The repo can go private later; its forks and clones would remain.
- **See:** decision 0008, SPEC.md sections 4, 15 and 20
