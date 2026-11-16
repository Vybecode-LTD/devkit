# Handoff

Overwritten every session. 2026-11-16, evening (Claude Code, the owner's machine, mostly over Remote Control): K3 began with storage (#58) and email (#59), the kernel's mails became templates (#60), the progress record and visual ledger the owner asked for landed (#61), and the owner decided the rename to MechFrame (decision 0034). Then this page (#62).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 (OAuth, invites and API keys, abuse protection and deletion) wait until the site needs them (decision 0029).
- **K3, in decision 0029's order:**
  - **Storage** (#58, decision 0032; `kernel/storage.py`, contract `dev plans/contracts/k3-storage.md`): a private bucket reached only through signed links (5 minutes unless asked, 6 hours at most, always a download), an optional public bucket at `STORAGE_PUBLIC_URL`, unguessable keys for a provider's files, inline only for five raster types whose bytes match. Tested with moto; `kernel/tests/test_storage_live.py` runs against a real store when `TEST_STORAGE_*` is set.
  - **Email** (#59, decision 0033; `kernel/email.py`, `kernel/mail_adapters.py`, contract `dev plans/contracts/k3-email.md`): `email.send(template, to, context)`; a module's templates in `emails.py`'s `EMAILS`, which a site rewords through `create_app(emails=...)`. **SMTP first** (`SMTP_HOST` set); Resend only where the host blocks SMTP (`RESEND_API_KEY` alone), the owner's rule. Failures are `MailError` with `retryable`, for jobs.
  - **The kernel's 19 mails are `kernel.*` templates** (#60; `kernel/auth/mails.py`, contract `dev plans/contracts/kernel-auth-templates.md`), word for word what they said (`kernel/tests/auth/mail_wording.json`), HTML included when a site gives some.
- **Progress** (#61): `docs/progress.json` is the one record; `python -m tools.progress` writes `docs/PROGRESS.md` and the rows of the owner's [visual ledger](https://claude.ai/artifact/48auLkb7Ajmyn2SNAni9rm) (private until they share it). Republish steps: `dev plans/progress-ledger/README.md`. v1.0: 33% (19 of 56 steps); everything: 13% (19 of 144). Republished at the end of this session.
- **Rename to MechFrame after K3** (decision 0034): repo to github.com/mechframe/mechframe, CLI `mechframe` plus `mf`, the Python import stays `kernel`, cookies `__Host-mf_*`, variables `MECHFRAME_*`, skills `mechframe-*`. Keep the DevKit name until that PR.
- **Tests:** last local full run 1026 passed, 6 skipped (5 live storage, 1 symlink), 27 strict expected failures; coverage 97.95%. CI passed on `main` at a1d0155.
- **GitHub:** public `Vybecode-LTD/devkit`. A PR lands by fast-forwarding `main` to its head once "CI result" is green, with the owner's OK for that PR. Codex reviews a PR's first push; CodeRabbit's free tier is often rate-limited.

## Next

1. **K3 jobs, contract first** (`C:\DEV\_templates\feature-CONTRACT.md`; the owner approves its goal and non-goals): the Postgres queue (`FOR UPDATE SKIP LOCKED`), `jobs.enqueue(name, payload, run_at)`, `@jobs.scheduled(cron)`, the scheduler's lock, budgets and retries (SPEC 6; `KICKOFF.md` K3; lift from VybeSite `worker.py`). Mail moves onto it, retried by `MailError.retryable`; unverified accounts are removed after 7 days. The K3 gate needs a job that survives a worker restart. ffmpeg in the worker image comes with discography (`kernel-additions.md` item 4).
2. Then events, audit, notifications, moderation, public rendering, and K3's gate.
3. **The rename PR** (decision 0034), then K4, K5, the ten hooks, and the site's steps 1 to 7.

## Open questions for the owner

- Decisions 0032 and 0033's own calls: links of 5 minutes unless asked and 6 hours at most, `get`'s 32 MiB, `STORAGE_MAX_BYTES` 2 GiB, three tries per storage call; `string.Template` rather than a template engine, a rewording limited to the original's placeholders, Resend's 10 s and SMTP's 15 s timeouts, TLS always. Keep them?
- When to make the R2 test buckets for `test_storage_live.py`: before the site's step 2.
- Desk steps: reset the Postgres `postgres` password (the owner types it); `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` if wanted.

## Notes

- **Bringing a PR branch up to date:** the auto-mode classifier refuses `git push --force-with-lease`; merge `main` into the branch and push normally (#61 did).
- **Every PR that changes a step's status updates `docs/progress.json`** and runs `python -m tools.progress`; the rows embed the tool's own code, so editing `tools/progress.py` makes them stale too.
- **The kernel's mails render through the installed templates** (`email.install`, done by `create_app`): the latest app built is the one rendering, which tests rely on.
- Git Bash collapses `\\` in heredocs and Write/Edit decode `\u` escapes: write scripts with the Write tool and build such characters with `chr()`.
- Race and lock-order tests must really race; never hand an ORM row past the route (memory notes).

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions and split account tables differ from the spec: port the behavior, not the shape.
