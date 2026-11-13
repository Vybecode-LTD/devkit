# 0015: How CI wires the quality gate

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** The audit of 2026-11-12 found the gate in SPEC.md 16 only partly wired:
  - CI ran only on pull requests, and none existed yet, so it had never run. A direct push to `main` skipped it, gitleaks included.
  - Coverage had no floor.
  - mypy left module backends unchecked.
  - Nothing re-checked unchanged pins against new advisories.
  - The Playwright, axe, server-copy and token rows can't run before there are pages, but section 16 didn't say so.

  Decision 0011 also claimed that gitleaks and the brand check ran on every PR.
- **Decision:**
  - CI runs on pull requests into `main` (only the jobs a change touches), and on every push to `main`, every Monday and by hand (every job).
  - Tests fail under 85% line coverage, section 16's default floor, measured over the kernel, the harness and the tools. Each module's own floor joins when its tests do.
  - mypy is strict on everything it checks, which now includes `modules/*/backend`.
  - pip-audit runs once per run, not once per Python. gitleaks is the release binary, checked against a pinned SHA-256.
  - Section 16's end-to-end, accessibility, public-pages and tokens rows run from K4, with the first pages.
  - The brand check stays local (CLAUDE.md).
- **Alternatives:**
  - A ruleset requiring "CI result" on `main`. That's the stronger guard, and it's the owner's call (a repo setting). **Applied 2026-11-13:** the ruleset `main` requires "CI result" on the exact commit, with the branch up to date for PR merges, and blocks force pushes and deletion. It has no "require a pull request" rule, because that would push every merge through GitHub's merge button, which stamps the API token's address on the commit. A commit can only carry a green "CI result" if CI ran on it first, on a branch, so the check rule gives the same guarantee.
  - SHA-pinned actions. They need something to keep them current (Dependabot), which is another bot on the repo: the owner's call. **The owner said yes (2026-11-13):** every action is pinned to a commit SHA with its version beside it, and `.github/dependabot.yml` opens one grouped PR a week.
- **Consequences:** Every merge to `main` costs a full run, about ten minutes, which is free on a public repo. Decision 0011 is reworded to match.
- **See:** SPEC.md 16; decisions 0008 and 0011; `.github/workflows/ci.yml`
