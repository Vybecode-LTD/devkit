# Next session: K3's gate, then the rename to MechFrame

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-17-next-session-k3-gate.md and follow it, starting with section 4."

## 1. The project

AI DevKit (MechFrame after K3, decision 0034): website modules around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo; nothing deployed.

## 2. Rules that aren't in a CLAUDE.md

- Pushing and landing are your call here (`CLAUDE.md` Rules): land by fast-forward when "CI result" is green on the head, no thread is open and the bots have nothing open. Auto-fix may be on: it wakes you on failures and comments, not on green. Never poll CI yourself.
- Stage by name; `gitleaks git --pre-commit --staged` first.
- **Don't edit CI's security gates** (the auto-mode classifier refuses it, rightly): the picomatch question below is the owner's.
- Keep the DevKit name until the rename PR, and let no PR mix the two names.

## 3. State (verified at the end of 2026-11-17)

- `main` at the head of #74 (the handoff), after #73 (public rendering, decision 0041). No open PRs. `C:\DEV\knowledge\owner.md` is uncommitted: the owner's.
- Last full run: 1,689 passed, 8 skipped, 27 xfailed, coverage 98.50 %.
- **main's push runs fail** on `npm audit` (picomatch, GHSA-fc5q-39xc-vjpf, no fix, dev tooling only); PRs touching no web path skip that job. An expiring allowlist is parked in `dev plans/npm-audit-allowlist/`.

## 4. The job, in order

1. **K3's gate** (KICKOFF K3; `docs/progress.json` K3 `gate`): tests for each service, an event delivered once to a handler safe to run twice (#65), a job surviving a worker restart (#63). Find each test, run it, and say what covers every service. Run `module-contract-lint` on the kernel, the brand check, gitleaks, pip-audit. Set `gate_passed` and rerun `python -m tools.progress` only on that evidence.
2. **The rename PR** (decision 0034), one mechanical PR: prose, packages, cookies (`__Host-mf_*`), `DEVKIT_*` to `MECHFRAME_*`, skills, links; the import stays `kernel`. Full suite and contract suite. It is not outward-facing, but the owner's steps go with it: create the `mechframe` GitHub organization, transfer the repo, install Codex and CodeRabbit there, rename the account's `devkit-*` skills. Ask when they'll do them.
3. Then K4 (the admin shell to decision 0040; mount with `createRoot`, style or hide `[data-server-copy]`; the Playwright parity test with the first React page), K5, the ten hooks, the site's steps 1 to 7.

## 5. Questions for the owner (ask; don't decide)

- Retention and the AI client are `later` in `progress.json` but in KICKOFF's K3 table: is the gate checked without them?
- Adopt the npm audit allowlist, or leave main red until picomatch ships a fix?
- Decisions 0032 to 0039's own calls (`docs/HANDOFF.md`): keep them? The R2 test buckets, and the desk steps (the `postgres` password; `Set-ExecutionPolicy`).
- Settled 2026-11-17 by the owner: member pages stay `noindex`, not disallowed in robots.txt.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, 11 to 16 minutes, `run_in_background`, logged to the scratchpad. Mutants edit source: nothing else running, then `git status`.
- Long heredocs with quotes break the Bash tool: use the Write tool. Files are CRLF. A command ending in `&` gives no notification. Git Bash rewrites `gh api /path`: omit the slash. The brand check bans some short phrases, test data included.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decision 0041; `dev plans/contracts/k3-public-rendering.md`; memory in `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0042, PR #75, migration `kernel_0011`.

## 8. Candidates for `knowledge/`

1. A surviving mutant may be redundant output but real behaviour: test that the code isn't called, don't delete it (`verify-real-pass`).
2. httpx drops a HEAD body itself: test HEAD middleware on raw ASGI messages.
3. robots.txt: a wildcard Disallow for member routes closes public routes sharing the prefix, `$` rules miss query URLs, and a blocked page can't show `noindex` (`server-copy-for-crawlers`).
4. A test's sentinel can sit inside a random id (`abc` in `shop-abc88e5e`).
5. `gh api /path` in Git Bash becomes `C:/Program Files/Git/path` (`windows-shell-and-tool-traps`).
