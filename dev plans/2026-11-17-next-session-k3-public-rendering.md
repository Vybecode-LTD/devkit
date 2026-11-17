# Next session: K3 public rendering, from its approved contract

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-17-next-session-k3-public-rendering.md and follow it, starting with section 4."

## 1. The project

AI DevKit (MechFrame after K3, decision 0034): website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`; nothing deployed. Vibrant Mindz waits on it (decision 0029).

## 2. Rules that aren't in a CLAUDE.md

- The contract is approved (the owner, 2026-11-17, all five answers): build it as written; a name or route that must change goes in its "Changes after approval" and the handoff. Check `docs/contracts/auth-api.md` and the contract suite before naming a route.
- Commit with the no-reply address; stage by name; `gitleaks git --pre-commit --staged` first.
- Pushing and landing are this session's call (`CLAUDE.md` Rules): land when "CI result" is green on the head and the bots have no open findings. Auto-fix may be on: it wakes you on findings, not on a green run.
- nh3 is a new dependency: hash-pinned (`CLAUDE.md` Commands), justified in the PR, and in `docs/TESTING.md` and the Stack.
- Keep the DevKit name until the rename PR.

## 3. State (verified 2026-11-17, end of session)

- `main` at the head of #71 (K3 moderation, landed by fast-forward); its branch deleted.
- **#72** (`docs/handoff-k3-public-rendering`: `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md`, decision 0040, SPEC Q11, the approved public rendering contract, this file) is the only open PR. If it's still open, land it as above.
- Last local full run: 1523 passed, 7 skipped, 27 xfailed, coverage 98.38 %. Nothing is half-done.
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner's to commit.

## 4. The job, in order

1. If #72 is still open, land it; then `git switch main`, `git pull --ff-only`, and branch `feat/k3-public-rendering`.
2. **Build `dev plans/contracts/k3-public-rendering.md`**, tests first (`kernel/tests/test_server_copy.py`, `test_shell.py`): `kernel/server_copy.py`, `kernel/shell.py`, `InstalledModule(pages=...)` checked against `routes.public`, the catch-all route registered last, `WEB_DIST`, the `kernel.site` settings section, the kernel files, the template's `server_copy.py`, decision 0041, SPEC 6, 7 and 9. Read the skill `server-copy-for-crawlers` and VybeSite's `site_routes.py`, `spa.py`, `site_html.py` and `routers/sitemap.py` (`C:\DEV\VybeSite\vybesite\backend\app\`; never its `dev plans\` or `snapshots\`). Then the full suite, mutants (section 7's list), PR #73.
3. Then K3's gate (KICKOFF), then the rename PR.

## 5. Questions for the owner (ask; don't decide)

- Decisions 0032 to 0039's own calls (`docs/HANDOFF.md`, Open questions): keep them?
- When to make the R2 test buckets; the desk steps (the `postgres` password; `Set-ExecutionPolicy`).

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, 10 to 18 minutes: `run_in_background`, logged to the scratchpad. Never `--cov=kernel.<module>`.
- After `db.rollback()` keep plain ids and reload rows. An `ON CONFLICT` on a partial index takes a literal predicate.
- Write/Edit turn a typed backslash-u escape into the real character: build JSON-LD escapes with `chr(92)`, and NULs in tests with `chr(0)`.
- Long heredocs with quotes break the Bash tool: write scripts with the Write tool. Working-tree files are CRLF.
- Extract an archive with Python given a Windows path: `/c/...` lands in `C:\c\...`.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decisions 0039, 0040; `dev plans/contracts/k3-moderation.md`, `k3-public-rendering.md`; #71's threads.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0041, PR #73, migration `kernel_0011`.

## 8. Candidates for `knowledge/`

1. `ON CONFLICT ... WHERE` on a partial unique index needs the predicate literal: a bound value stops matching from a prepared statement's sixth (generic) run (`supabase-auth-and-rls-traps` or a Postgres note).
2. A rank check between two people locks both rows, in id order, and re-checks the actor: two owners can't remove each other at once.
3. `str.isdigit()` takes "²"; ids from the outside take `isascii() and isdigit()`.
4. An approved contract can still miss an earlier one: grep the API docs and contract tests for the route first.
5. Python given `/c/...` from Git Bash resolves to `C:\c\...` (`windows-shell-and-tool-traps`).
