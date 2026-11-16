# Next session: K3, the kernel services, storage first

Run from `C:\DEV\AI-DevKit` in Claude Code: "Read dev plans\2026-11-16-next-session-k3-storage.md and follow it, starting with section 4."

## 1. The project

AI DevKit: website modules an agent copies into a site, around a FastAPI + Postgres kernel (`CLAUDE.md`, `SPEC.md`). Public repo `Vybecode-LTD/devkit`. Nothing is deployed. The owner's Vibrant Mindz site (`C:\DEV\VM Website`) waits on these modules (decision 0029).

## 2. Rules that aren't in a CLAUDE.md

- **Landing needs the owner's OK for each PR:** once "CI result" is green and the bots have no open findings, `git push origin <sha>:refs/heads/main`, then delete the branch locally and on GitHub. If CodeRabbit skips or is rate-limited, green CI plus Codex's first-push review is enough.
- Commit with the no-reply address on `main` (`git log -1 --format=%ae`). Stage by name; run `gitleaks git --pre-commit --staged` first.
- A kernel service is a seam: write its one-page contract first (`C:\DEV\_templates\feature-CONTRACT.md`). A spec change is a decision record plus a change-log line.
- Only the owner touches the Postgres superuser, `pg_hba.conf` (never `trust`), the execution policy, and any real storage or mail keys.

## 3. State (verified 2026-11-16, end of session)

- `main` is at b9a6939 (#56). #52 to #56 landed today; their branches are deleted.
- **#57** (`docs/vm-step-0-handoff`: `docs/HANDOFF.md`, `CLAUDE.md`/`AGENTS.md`, this file) is the only open PR.
- 823 passed, 1 skipped, 27 xfailed, coverage 97.0% (Windows); contract suite 128 passed, 27 not built. CI passed on b9a6939. Nothing is half-done.

## 4. The job, in order (one PR each, tests first)

1. If #57 is open, ask the owner whether to land it once "CI result" is green; then `git switch main` and `git pull --ff-only`.
2. **Ask the owner how storage is tested** (`docs/HANDOFF.md`, Open questions, first item) before writing it.
3. **K3 storage:** `storage.put / get / signed_url` (SPEC 6), boto3 against an S3-compatible store (SPEC 2), the rules in SPEC 15 and `docs/plans/vibrant-mindz-backend/kernel-additions.md` item 3. boto3 is synchronous: keep it off the event loop. Lift from the sources in `KICKOFF.md` K3 (where each lives: `docs/private/inventory.md`) and run the brand check. A new dependency: `requirements.in`, re-pin with hashes, `pip-audit`, the Stack line in `CLAUDE.md` and `AGENTS.md`.
4. Then the rest of K3 in `docs/HANDOFF.md`, Next, item 1: email, jobs, events, audit, notifications, moderation, public rendering, and K3's gate.

## 5. Questions for the owner (ask; don't decide)

- Storage tests: moto in-process, or a local MinIO?
- Keep decision 0030's own calls, and 0028, 0026 and 0027's (`docs/HANDOFF.md`, Open questions)?
- Eight leftover test databases on the local Postgres: drop them?
- Desk steps: reset the `postgres` password (they type it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if they choose.

## 6. Environment and traps

- Tests: `TEST_DATABASE_URL="postgresql://devkit:devkit@localhost:55432/postgres" DEVKIT_REQUIRE_DB=1 .venv/Scripts/python.exe -m pytest --cov=kernel`, about 7 minutes, in the background, logged to the scratchpad. The contract suite alone: 90 seconds.
- Git Bash collapses `\\`, runs backticks in double quotes, and `sed -i` strips CRLF (`CLAUDE.md` and `AGENTS.md` are CRLF): write scripts and PR bodies with the Write tool, run with `.venv/Scripts/python.exe -I`.
- Mutants: a scratchpad script swaps one string, runs the named tests and restores the file.

## 7. Evidence, memory and next IDs

- `docs/HANDOFF.md`; decisions 0029 to 0031; `docs/plans/vibrant-mindz-backend/`; the bodies of #52 to #56.
- Memory: `C:\Users\vybec\.claude\projects\C--DEV-AI-DevKit\memory\`.
- Next free IDs: decision 0032, PR #58, migration `kernel_0006`.

## 8. Candidates for `knowledge/`

1. Park scaffolds where the harness and linters don't look (a leading `_`) until built (`devkit-module-extractor`).
2. CodeRabbit's free tier skips PRs over 100 files; a stacked PR counts its base's (`git-and-ci-traps`).
3. Under a lock, re-read only the column you check: `populate_existing` can overwrite what a later compare-and-swap needs (`auth-threat-model-checklist`).
4. A route that waits on a lock re-checks its session after it (`auth-threat-model-checklist`).
