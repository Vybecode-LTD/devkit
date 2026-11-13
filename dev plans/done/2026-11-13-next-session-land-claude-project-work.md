# Next session: land the claude.ai project's work (a skill, the module roadmap, decision 0018, the account skills)

Run from `C:\DEV\AI-DevKit` in Claude Code. Say: "Read dev plans\2026-11-13-next-session-land-claude-project-work.md and do it."

This is a short session that runs **before** `dev plans\2026-11-13-next-session-k2-in-claude-code.md`. When it's done, this prompt moves to `dev plans\done\` and the K2 prompt is the job again.

## What came in

On 2026-11-12 and 13 the owner worked in his claude.ai project "AI DevKit": about 140 module ideas, his Must / Want / Later / Nah picks, a roadmap built from them, ten contract hooks to add before v1.0 freezes, and a new skill to add them. None of it is in the repo yet. All of it is in `docs\private\claude-project-2026-11-13\` (gitignored). **Read its `README.md` first:** it maps every file to where it goes.

In short:
- `devkit-hook-designer.patch`: the new skill, its row in CLAUDE.md and AGENTS.md, and `docs/SKILL-BACKLOG.md` updated. Made against `main` at 9aa4562.
- `drafts\docs\plans\module-roadmap.md` and `drafts\docs\decisions\0018-module-roadmap-and-contract-hooks.md`: ready to land, already scrubbed for the public repo.
- `account-skills\`: the 16 skills from the owner's claude.ai account that came out of this project.
- `module-picks-2026-11-13.md` and `project-docs\`: reference only. They stay where they are.

## Before anything

1. `git status` must be clean, on `main`, level with `origin/main`. If there is uncommitted K2 work, stop and ask the owner. Don't stash it, and don't mix it into these PRs.
2. The set-up in the K2 prompt applies (venv, `npm ci`, `TEST_DATABASE_URL`). Run the suite once, and if the numbers differ from the K2 prompt's, find out why first.
3. **Windows:** use `npm.cmd` and `.venv\Scripts\python.exe -m ...` if PowerShell blocks scripts. Claude Code's shell is Git Bash.

## The job, in order

Each PR gets its own branch. Land each one as the K2 prompt's Git section says: open the PR, wait for "CI result" to go green, fast-forward `main` to the PR head (`git push origin <sha>:refs/heads/main`), then delete the branch. Commits use the owner's GitHub no-reply address (decision 0011). Never push straight to `main`.

### PR 1: the `devkit-hook-designer` skill (branch `docs/skill-devkit-hook-designer`)

1. `git apply --3way "docs/private/claude-project-2026-11-13/devkit-hook-designer.patch"`. If a hunk conflicts because CLAUDE.md, AGENTS.md or `docs/SKILL-BACKLOG.md` moved on since 9aa4562, keep both sides: the repo's newer lines plus the patch's added rows.
2. Check the result:
   - `skills/devkit-hook-designer/SKILL.md` exists.
   - The project-skills tables in CLAUDE.md and AGENTS.md have its row, and the two files are still identical below line 1.
   - `docs/SKILL-BACKLOG.md` lists it under Built and the seven roadmap ideas under Waiting: `booking-availability-engine`, `license-key-server`, `wordpress-to-devkit-migrator`, `entitlements-gating`, `consent-gated-scripts`, `module-idea-scorer` and `picks-to-build-plan`.
   - Then add one more row under Waiting, raised after the patch was made: `claude-project-handoff` | Exports a claude.ai project (its docs, picks, account skills and decisions) into a local repo's `docs/private/`, scrubs drafts for a public repo, and writes the Claude Code prompt that lands them. Done by hand on 2026-11-13 for this session | 2026-11-13 | No |
3. Read the skill once against the repo as it is today. Its "first batch" table describes SPEC.md on 2026-11-13. If anything has changed since, correct the skill, because the spec wins.
4. `python -m tools.link_skills`, then the full gate: ruff, black, mypy, `python -m tools.validate_schemas`, pytest with `--cov`, `npm test`, and `gitleaks git --pre-commit --staged`.
5. Commit: `docs(skills): add devkit-hook-designer and log the roadmap skill ideas`.

### PR 2: the module roadmap and decision 0018 (branch `docs/module-roadmap`)

1. Copy `drafts\docs\plans\module-roadmap.md` to `docs\plans\module-roadmap.md`, and `drafts\docs\decisions\0018-module-roadmap-and-contract-hooks.md` to `docs\decisions\`.
2. **Public-repo check before staging.** The repo is public. Neither file may name the client or anything listed in `docs\private\README.md`, any project not already named in the repo, or personal details. The drafts were scrubbed, so verify rather than rewrite. Run the brand check too.
3. Add a row to the index in `docs/decisions/README.md`: `| [0018](0018-module-roadmap-and-contract-hooks.md) | The module roadmap after v1.0, and the contract hooks it needs | Accepted; hooks not yet applied |`.
4. CLAUDE.md and AGENTS.md, keeping them identical below line 1:
   - Add `docs/plans/module-roadmap.md` to the project map.
   - Add a line under "Current state": the post-v1.0 roadmap and ten contract hooks are decided (0018). The hooks land with `devkit-hook-designer` after the kernel phases and before blog, chat and payments are extracted (SPEC 19, phase 3), so the validation extractions exercise them too.
5. `docs/HANDOFF.md`: under "Next", after K2, add the hooks (one PR per hook, starting with export and erase, which is nearly done) and point to the roadmap.
6. Move this prompt into `dev plans\done\` as part of this PR (it's untracked until then, so a plain move and `git add` does it).
7. No SPEC.md change in this PR, so no change-log line. Each hook PR adds its own line naming 0018.
8. Commit: `docs(plans): record the module roadmap and the contract hooks (decision 0018)`.

### Step 3: the owner's account skills (no PR)

`docs\private\claude-project-2026-11-13\account-skills\` holds 16 skills.

- **Seven are already in `skills\`** (six, plus `devkit-hook-designer` after PR 1). The repo copies lead. Don't copy the account versions over them: they're older. `devkit-module-extractor`'s account copy even names the client folder, so it must never go anywhere public.
- **The other nine are general-purpose:** `server-copy-for-crawlers`, `auth-threat-model-checklist`, `spec-to-kickoff`, `supabase-rls-to-fastapi`, `doc-and-repo-spec-sync`, `pytest-throwaway-postgres`, `conditional-settings-saves`, `path-filtered-ci` and `remote-device-git-sync`.
  - Make them available to every Claude Code project by copying each folder to `%USERPROFILE%\.claude\skills\<name>\`.
  - If a folder of that name is already there, diff the two and ask the owner which to keep. Never overwrite silently.
  - Don't add them to this repo's `skills\` unless the owner asks. If he does, each one goes through the public-repo check first.
  - `auth-threat-model-checklist` is worth running on every K2 auth PR from here on. `doc-and-repo-spec-sync` no longer applies to DevKit (decision 0017) but stays useful elsewhere.

### Step 4: wrap up

- Update CLAUDE.md and AGENTS.md "Last Completed Task" (in PR 2 if it's still open, otherwise a one-line follow-up).
- Tell the owner:
  - both PR numbers;
  - that SPEC.md didn't change yet (the hooks come later);
  - which of the nine skills were installed, and any that needed his call.
- Then the job is K2: `dev plans\2026-11-13-next-session-k2-in-claude-code.md`.

## Rules that bite here

- **Public repo.** Nothing from `docs\private\` gets committed. The drafts are the only files that leave that folder, and only after the check in PR 2.
- **Skills:** don't build new ones. A new idea goes into `docs/SKILL-BACKLOG.md`; the owner asked for every suggestion to be logged there.
- **The spec is the contract.** If something in the drafts disagrees with SPEC.md as it stands, the spec wins. Fix the draft and tell the owner.
