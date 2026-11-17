# Handoff

Overwritten every session. 2026-11-17, morning Eastern (Claude Code, the owner's machine): K3 audit (#67, decision 0037), contract first, approved by the owner with the four answers recommended; landed by this session. Then this page (#68).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3, in decision 0029's order:** storage (#58, 0032), email (#59, 0033), the kernel's mails as templates (#60), jobs (#63, 0035), events (#65, 0036), and now **audit** (#67, 0037; contract `dev plans/contracts/k3-audit.md`):
  - **One table, `kernel_audit_event`:** auth's `auth_audit_event` renamed by `kernel_0008`, rows kept, plus `target_type`/`target_id` and indexes by actor and target. The model is in `kernel/models.py`; `kernel.auth.models` re-exports it (and `kernel.models` imports auth's models last, for that).
  - **`audit.record(db, action, *, actor, target=, subject=, result=, details=, request=)`** adds a row to the caller's session, synchronous. Actions `<owner>.<name>`; the kernel's are `audit.KERNEL_ACTIONS`, which `test_every_kernel_audit_call_names_a_kernel_action_and_each_is_used` holds equal to the code's calls: **a new kernel audit action goes in that set in the same PR**. A module's owner must be installed (`assemble` calls `audit.install`). Details refuse `@`, a key with a `password`/`secret`/`token`/`code` part, non-JSON and over 4 KiB. Auth's `record`/`record_by_kernel` wrap it.
  - **Readers:** `GET /api/kernel/admin/audit` (`auth.audit.read`, behind the admin gate, so the staff path is under `/admin`: a contract change after approval) and `GET /api/auth/activity` (own `auth.*` entries, `by_you`). SPEC 7's list shape, `?cursor=&limit=` and `{items, next_cursor}`, keyset on `(at, id)`.
  - **Pruning:** `kernel.prune_audit` nightly, `AUDIT_KEEP_DAYS` (365, at least 30). **Triggers** refuse UPDATE and TRUNCATE, and DELETE unless the transaction set `kernel.audit_prune`. Details and target ids refuse a NUL (Postgres would at the flush) and `@` in keys too.
  - `settings.save` records `kernel.settings_saved` (`{version, changed, via}`, names only).
- **Review of #67:** Codex found an overflowing cursor (61d187c); CodeRabbit found the list names, NUL, an address key and TRUNCATE (0005271), then was rate-limited on the last commit. All threads resolved.
- **Tests:** last local run 1382 passed, 7 skipped (5 live storage, 1 symlink, 1 SIGTERM on Linux only), 27 strict expected failures; coverage 98.20 %, `audit.py` 100 %; 39 of 39 mutants killed. CI passed on `main` at 0005271.

## Next

1. **K3 notifications, contract first** (`C:\DEV\_templates\feature-CONTRACT.md`): `notify(user, key, context)` (SPEC 6), in-site and email by each person's preferences per key, built from module.json's `notifications` (SPEC 5; `schema/module.schema.json`), with one-click unsubscribe. KICKOFF K3 says new, with Basefra.me's notification center for ideas. Mail goes through `email.queue`; the scaffolds in `modules/_*` declare keys.
2. Then moderation (it emits `auth.user.suspended` and records its actions, with a narrower audit view for moderators: the owner's answer on #67), public rendering, K3's gate; then **the rename PR** (decision 0034).
3. Then K4 (the Audit log page and the account page's activity list read #67's routes; the System page reads dead jobs), K5, the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Still open from earlier sessions: decision 0036's own calls (a listener's 300-second timeout; `auth.user.verified` on an email change's confirmation too; no deliveries for a module `MODULES` leaves out), 0035's, 0032's and 0033's; when to make the R2 test buckets; the desk steps (the `postgres` password; `Set-ExecutionPolicy` if wanted).
- `C:\DEV\knowledge` has `owner.md` uncommitted (the push-and-merge rule and an older Boston-time line): the owner commits it.

## Notes

- **Audit in tests:** entries share the run's database; give each test a target kind, actor or subject of its own and filter on it. A test that needs old entries inserts them with an explicit `at` (the clock only moves forward). Staff routes need a confirmed second factor on the staff account (a `Totp` row). A new kernel audit action joins `audit.KERNEL_ACTIONS` in the same PR.
- **Lists** follow SPEC 7: `?cursor=&limit=` in, `{items, next_cursor}` out (CodeRabbit caught #67 using other names).
- **Coverage on one module:** `--cov=kernel.audit` breaks the run (it loads the kernel before the root conftest); use `--cov=kernel`.
- Kernel events in tests: the `heard` fixture. Due jobs: `Draining`. A test that moves the clock runs only its own jobs.
- Git Bash: `cat > file` with nothing piped in waits for ever; a heredoc holding `'''` can break `bash -c`: write scripts with the Write tool. Git Bash's `sed -i` drops CRs. A subprocess on Windows needs `sys.executable`.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
