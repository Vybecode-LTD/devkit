# Next session: K4's gate

Run from `C:\DEV\AI-DevKit`: "Read dev plans\2026-11-20-next-session-k4-gate.md and follow it, starting with section 4."

## 1. The project

MechFrame is a set of website modules built around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). The repo is public, mechframe/mechframe. Nothing is deployed.

## 2. Rules not in a CLAUDE.md

- **K4's contract** is approved (`dev plans/contracts/k4-web-kernel.md`). The next change after approval is 21.
- **Landing:** push once the local suites are green and batch the fixes. Land by fast-forward once "CI result" is green and no thread is open. Stage by name and run gitleaks on the staged diff.
- **A gate is evidence, not new work.** Where a check falls short, say so and ask the owner before building anything.
- **`AGENTS.md` holds `CLAUDE.md`'s text:** change both together.

## 3. State (2026-11-20, morning Eastern; check, don't trust)

- **main** is `a1f89e6`, #87's head (K4.8). Check it with `git log -1 origin/main`.
- **#88** (`k4-role-changed-event`) holds the role-change event, K4.8 marked done, and this handoff. It was open with CI running. Check it with `gh pr view 88`.
- **Tests:** #87's head had Vitest 490, Playwright 73 and CI green. #88 passed 2,126 Python tests locally.
- **The ledger's** `steps` dataset still points at `41c2879`'s rows.

## 4. The job

1. **Land #88** if it is still open, then delete its branch. Republish the ledger from `main` (`dev plans/progress-ledger/README.md`).
2. **K4's gate** (contract §7; the K4 `gate` in `docs/progress.json`). On `main`, run the whole Python suite with coverage (95 % or more), `npm.cmd run test:coverage` (85 %), lint, typecheck, build and the full Playwright suite. Then run `python -m tools.themes --check`, `tools.openapi --check` and `tools.event_schemas --check`.
   - Match each §7 bullet to its tests by name, from `kernel/tests/e2e/` (`sign-in`, `admin`, `parity`, `kit`).
   - Check that the screens are in `dev plans/2026-11-19-k45-screens/`, `k46-admin/`, `k47-people-roles/` and `k48-settings-system/`.
   - Run `module-contract-lint` on the kernel.
   - Write `dev plans/<date>-k4-gate-evidence.md` the way K3's was written (`dev plans/2026-11-17-k3-gate-evidence.md`).
   - If everything passes, set K4's `gate_passed` and run `python -m tools.progress`. One docs PR.
3. **Then K5** (`KICKOFF.md`): write its contract first (`_templates/feature-CONTRACT.md`) and get the owner's OK.

## 5. Ask the owner

- A name for a person (nothing sets `display_name`)? A way for a site to reword the kernel's screens?
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps.
- Rename `C:\DEV\AI-DevKit` and the `devkit-*` skills? Carry `line-3` and the tint aliases back to VM Website?
- cubic is at its trial limit: pay, or drop it? Delete the unused ledger asset `cd100445…`? The stray `C:\dev plans\` is theirs to delete.

## 6. Environment and traps

- **Python tests:** run them in Git Bash, in the background, into a log: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" MECHFRAME_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel` (12 to 14 min). Change no file while it runs.
- **One Playwright test:** pick it by `file:line`, because `-g` with a space breaks.
- **Paths:** Playwright resolves them from the config's folder.
- **Flaky under load:** K4.7's role e2e and `test_an_undo_link_outlives_the_owners_reset`. Re-run one alone before calling it red.
- **Scripted edits:** tool parameters decode `\n` and `\uXXXX`. Edit with a Python script that keeps the file's newline.

## 7. Evidence and next IDs

`docs/HANDOFF.md`, the contract's changes 19 and 20, decisions 0045 and 0046, and the bodies of #87 and #88. Next free: decision 0047, PR #89, migration `kernel_0013`, contract change 21.

## 8. Candidates for `knowledge/`

1. A form that saves while the person types keeps three snapshots: the read, the version the edit began from, and what is in flight.
2. Retry a dead job as a new row. A worker that names its claim by (id, state, tries) can otherwise finish the new try.
3. Review bots rate-limit on quick pushes. Name a review skipped on the last head.
4. Playwright's relative paths start from the config's folder.
5. Coverage taken while files change reports wrong lines.
