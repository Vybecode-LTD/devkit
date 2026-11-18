# Handoff

Overwritten every session. 2026-11-17 night to 2026-11-18 morning Eastern (Claude Code, the owner's machine, the morning part with the owner): K3's gate checked and passed, npm audit's expiring allowlist adopted (#75), and AI DevKit renamed MechFrame (#76). The owner moved the repo to github.com/mechframe/mechframe and installed Codex, CodeRabbit and cubic there. The session landed #75 and #76 itself. Then this page (#77).

## State

- **K0, K1 done and audited; K2 steps 1 to 8 done** (#1 to #54). Steps 9 to 11 wait until the site needs them (decision 0029).
- **K3 done, gate passed** (#75; the evidence: `dev plans/2026-11-17-k3-gate-evidence.md`): storage, email, the kernel's mails, jobs, events, audit, notifications, moderation and public rendering, each with its tests and each service file at 100 % coverage. Both named tests: `test_events.py::test_an_event_reaches_its_listener_once_and_a_second_run_changes_nothing` and `test_worker.py::test_a_killed_worker_s_job_is_finished_by_the_next`. Retention and the AI client stay `later`, outside the gate (the owner, 2026-11-17).
- **npm audit** runs `python -m tools.npm_audit` (decision 0015, amended). It fails on any advisory not in `tools/npm_audit_allow.json`, on an entry past its `until` date or more than 90 days out, and on an entry npm no longer reports. It also fails on an allowed advisory that `npm audit --omit=dev` reports, and on a release of the package newer than the entry's `latest`. The one entry: picomatch GHSA-fc5q-39xc-vjpf, until **2026-12-17**, `latest` 4.0.7. A change to either file runs the Web job.
- **MechFrame** (#76, decision 0034):
  - The CLI is `mechframe` (also `mf`), with `mechframe.lock.json` as its lock file.
  - npm: `mechframe`, `@mechframe/kernel` and `@mechframe/harness-web`. The Python project is `mechframe`; **the import stays `kernel`**.
  - Wire names: cookies `__Host-mf_session` and `__Host-mf_device`, API keys `mf_live_…`, errors `urn:mechframe:problem:…`.
  - `MECHFRAME_REQUIRE_DB`, hosts `mechframe.test`, the skills `mechframe-*`.
  - Old names stay only in history: decision records, SPEC's earlier change-log lines, `dev plans/done/`, the contracts. They also stay in the folder `C:\DEV\AI-DevKit` and in the owner's local Postgres role `devkit` (port 55432). Compose and CI use `mechframe`.
- **The repo** is public at github.com/mechframe/mechframe. The `main` ruleset came with it, the old URL redirects, and the local remote points here. Reviewers: Codex, CodeRabbit (it skips a PR over 100 files) and cubic, which reviews every push and found real slips on both PRs.
- **The Vibrant Mindz owner decisions of 2026-11-17** are in `docs/plans/vibrant-mindz-backend/backend-plan.md` section 4, with the options that lost:
  - one primary-button hover, `#FF9447`; K4's admin shell hovers to the theme's accent-hover;
  - a Videos page at `/videos` in the site's step 2, with `featured_placement.video_kind` (kinds confirmed 2026-11-18);
  - cards, Apple Pay and Google Pay on Stripe's hosted Checkout at launch, with no domain step, PayPal later;
  - steps 6 and 7 designed after launch.

  The same section says how the site's theme moves in at K4.
- **Tests:** 1,705 passed, 8 skipped, 27 strict expected failures (K2 steps 9 to 11); coverage 98.48 %.

## Next

1. **K4, the web kernel** (KICKOFF K4; SPEC 8):
   - the app shell, `useSession()`, the typed client and `defineModule`;
   - the UI kit, the auth screens and themes;
   - the admin shell to decision 0040, its primary action hovering to accent-hover;
   - mount with `createRoot`, and style or hide `[data-server-copy]`;
   - the Playwright parity test with the first React page.

   It touches seams (the typed client, the module slots), so its contract comes first (`C:\DEV\_templates\feature-CONTRACT.md`).
2. Then K5 (the `mechframe` CLI and the site template, which sets `WEB_DIST`), the ten hooks, and the site's steps 1 to 7.
3. **By 2026-12-17:** recheck picomatch. Upgrade if a fixed release is out; otherwise renew the allowance on purpose, with its reason. The check fails on its own once a newer picomatch is published.

## Open questions for the owner

- Decisions 0032 to 0039's own calls, each listed in its record: keep them?
- When to make the R2 test buckets. The desk steps: the `postgres` password, and `Set-ExecutionPolicy` if wanted.
- Rename the folder `C:\DEV\AI-DevKit`? Claude Code's memory for the project moves with it. Also rename the claude.ai account's `devkit-*` skills (decision 0034).
- For the site's step 4: how many days links from new community members are held for a moderator (backend plan section 4, owner answers of 2026-11-18).
- `C:\DEV\knowledge\owner.md` is uncommitted: the owner commits it.

## Notes

- **npm's `fixAvailable` doesn't mean a fix shipped:** for picomatch it names a downgrade of vite to 6.2.7. A newer release of the package is the signal, and only a person can say whether it fixes the advisory.
- **A fresh org install of the review bots doesn't review a PR that's already open.** Comment `@codex review` and `@coderabbitai review` to start them; cubic reviews on its own.
- **A text-pass rename keeps real paths only if they're listed:** `AI-DevKit/docs/…` with no `C:\DEV\` before it became `AI-MechFrame/…` (cubic caught it).
- **The tool decodes `\n` inside a heredoc's Python strings into real newlines:** build escapes with `chr(92)`.
- **Never `--cov=kernel.<module>`**: it breaks the fixtures. Use `--cov=kernel`.
- Long heredocs with quotes break the Bash tool: write scripts with the Write tool. Working-tree files are CRLF.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code; it bans some short phrases, test data included.
- Editing CI's security gates is the owner's call: ask first, as #75 did.
