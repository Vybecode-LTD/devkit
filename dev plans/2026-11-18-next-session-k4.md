# Next session: K4, the web kernel (contract first)

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-18-next-session-k4.md and follow it, starting with section 4."

## 1. The project

MechFrame (AI DevKit until 2026-11-18, decision 0034): website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo github.com/mechframe/mechframe; nothing deployed. The Python import is still `kernel`.

## 2. Rules that aren't in a CLAUDE.md

- Pushing and landing are your call here (`CLAUDE.md` Rules): land by fast-forward when "CI result" is green on the head and no thread from Codex, CodeRabbit or cubic is open. Auto-fix may be on: it wakes you on failures and comments, not on green.
- Stage by name; `gitleaks git --pre-commit --staged` first.
- Changing CI's security gates is the owner's call: ask first.
- K4 touches seams (the typed client, `defineModule`'s slots, the admin shell's routes): write its contract from `C:\DEV\_templates\feature-CONTRACT.md` and get the owner's OK before code.

## 3. State (verified at the end of 2026-11-18)

- `main` at the head of #77 (the handoff), after #76 (the rename) and #75 (K3's gate, the npm audit allowlist). No open PRs. `C:\DEV\knowledge\owner.md` is uncommitted: the owner's.
- Last full run: 1,705 passed, 8 skipped, 27 xfailed, coverage 98.48 %. main's push runs are green again (def8a06's, after #75, the first since picomatch).

## 4. The job, in order

1. **K4's contract** (KICKOFF K4 lists the pieces; SPEC 8; decision 0040 for the admin shell, whose primary action hovers to the theme's accent-hover). Mount with `createRoot`, style or hide `[data-server-copy]`; the Playwright parity test with the first React page. Ask the owner its open questions, then build test-first, one logical change per PR.
2. The site's theme moves in at K4: `C:\DEV\VM Website\design\theme\vibrant-mindz\` README, "At K4" (copy `tokens.json`, `tokens.css` and the generator, rename to Machined Light's names, rerun the census there). Read `docs/plans/vibrant-mindz-backend/backend-plan.md` section 4 for the site's owner decisions of 2026-11-17.
3. Then K5 (the `mechframe` CLI, also `mf`; the site template sets `WEB_DIST`), the ten hooks, the site's steps 1 to 7.
4. **By 2026-12-17:** picomatch's allowance ends (`tools/npm_audit_allow.json`): upgrade if fixed, else renew on purpose.

## 5. Questions for the owner (ask; don't decide)

- K4's contract questions, when it's written.
- Decisions 0032 to 0039's own calls: keep them? The R2 test buckets; the desk steps (the `postgres` password; `Set-ExecutionPolicy`).
- Rename the folder `C:\DEV\AI-DevKit` (memory moves with it) and the account's `devkit-*` skills?
- The Videos page's kind names (`music-video`, `rap-battle`, `poetry`); and whether the Apple Pay domain step stays on the payments checklist (Stripe says hosted Checkout needs none: backend plan section 4).

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, 8 to 14 minutes, `run_in_background`, logged to the scratchpad. The local role is still `devkit`; compose and CI say `mechframe`.
- Web: `npm.cmd ci`, `npm.cmd run lint`, `npm.cmd run typecheck`, `npm.cmd test`, `npm.cmd run build`; `python -m tools.npm_audit`.
- CodeRabbit skips a PR over 100 files; cubic reviews every push.
- The Bash tool decodes `\n` in heredoc strings: build escapes with `chr(92)`. Long heredocs with quotes break: use the Write tool. Files are CRLF.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; `dev plans/2026-11-17-k3-gate-evidence.md`; memory in `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0042, PR #78, migration `kernel_0011`.

## 8. Candidates for `knowledge/`

1. npm's `fixAvailable` can name a parent's downgrade: a newer release of the package is the sign a fix may have shipped (`verify-real-pass` or a CI skill).
2. A rename by text pass keeps only the paths it lists: relative paths that hold the old name slip through.
3. Moving a repo to a new org: transfer, don't push into a new empty repo (PRs, rulesets and redirects come along); review apps need installing on the org (`git-and-ci-traps`).
4. A path filter must include the files a job's own check reads, or a change to them skips the check.
