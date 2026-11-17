# Handoff

Overwritten every session. 2026-11-17, evening Eastern (Claude Code, the owner's machine, mostly over Remote Control): K3 moderation (#71, decision 0039), contract first, five review findings fixed in the PR, landed by this session. The owner's admin-shell decision recorded (0040), the public rendering contract written and approved. Then this page (#72).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3, in decision 0029's order:** storage (#58, 0032), email (#59, 0033), the kernel's mails (#60), jobs (#63, 0035), events (#65, 0036), audit (#67, 0037), notifications (#69, 0038), and now **moderation** (#71, 0039; contract `dev plans/contracts/k3-moderation.md`, with its changes after approval):
  - A module declares what can be reported in `moderation.py`: `@moderation.kind("<id>.<entity>", actions=(...))` on a `moderation.Kind` with `describe`, `apply` and `dismissed` (default nothing), listed on `InstalledModule(reportable=...)`; the harness finds them by type.
  - One open case per thing (a partial unique index and an upsert, its predicate literal), the excerpt kept as first reported. `POST /api/kernel/moderation/reports` for verified accounts, 20 an hour.
  - Filters (settings section `kernel.moderation`: held terms, blocked domains, a link cap) hold text and never drop it: `screen`, then `hold`.
  - Actions under `kernel.moderation.act`: dismiss, hide, delete, a time-out (`auth_user.timed_out_until`, `Depends(moderation.can_post)`), and a ban, which suspends and also needs `auth.user.suspend` and a recent sign-in.
  - Suspension at `POST /api/auth/admin/users/{id}/suspend` and `/restore`: the actor's row and the person's locked in id order, a new session epoch, audited, mailed, emitted as `auth.user.suspended` and the new `auth.user.restored`.
  - The moderators' log (`GET /api/kernel/admin/moderation/log`) is decision 0037's narrower view. `kernel.prune_moderation` removes cases closed past `AUDIT_KEEP_DAYS`.
- **Decision 0040 (the owner):** K4's admin shell is built to the Vibrant Mindz canvas Admin design, styled by tokens, for every site; only its generic parts in the kernel; checked in the site's dark theme and Machined Light. It amends 0008 (SPEC Q11). The brief is `VM Website/design/specs/admin-look.md`.
- **Tests:** last local run 1523 passed, 7 skipped, 27 strict expected failures; coverage 98.38 %, `moderation.py` at 100 %; 21 of 21 mutants killed.

## Next

1. **K3 public rendering**, its contract approved with the five answers recommended (`dev plans/contracts/k3-public-rendering.md`): `kernel.server_copy`, one `page(db, path, params)` per page matched by `routes.public`, the shell and `WEB_DIST` with VybeSite `spa.py`'s rules, `sitemap.xml`, `robots.txt`, `llms.txt`, the `kernel.site` settings section, nh3 as the safety net. Predicted PR #73.
2. Then K3's gate (KICKOFF), then **the rename PR** (decision 0034).
3. Then K4 (the admin shell to decision 0040, the System page reading dead jobs and deliveries), K5, the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Decisions 0039's, 0038's, 0037's, 0036's, 0035's, 0032's and 0033's own calls, each listed in its record: keep them?
- When to make the R2 test buckets; the desk steps (the `postgres` password; `Set-ExecutionPolicy` if wanted).
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner commits it.

## Notes

- **An `ON CONFLICT` on a partial unique index** names its predicate as literal SQL (`text("status = 'open'")`): bound as a value, Postgres stops matching it once a prepared statement turns generic, from the sixth run.
- **Tests that roll back** keep plain ids and reload rows (`rollback-expires-orm-rows`); a race test holds the first lock and waits on `pg_stat_activity` until the second blocks.
- **Never `--cov=kernel.<module>`**: it breaks the fixtures. Use `--cov=kernel`.
- Long heredocs with quotes break the Bash tool: write the script with the Write tool and run it. Working-tree files are CRLF; scripts that edit them keep the file's line ending.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
