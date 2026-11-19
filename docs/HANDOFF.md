# Handoff

Overwritten every session. This one: 2026-11-19, morning to midday Eastern (Claude Code, the owner's machine). #82 had landed at `540056a`. K4.5, the sign-in and account screens, landed as #83 by fast-forward, this page in it.

## State

- **K0 to K3 are done.** K2 steps 9 to 11 wait (decision 0029).
- **K4** (contract `dev plans/contracts/k4-web-kernel.md`, decision 0042): five of its eight PRs are in: #78, #79, #80, #82 and #83.
- **#83, K4.5** (contract change 16, decision 0043):
  - **Backend, contract tests first:** the device routes (`kernel/auth/devices.py`; seven tests, seen failing as `NotBuilt`) and the new `GET /api/auth/security` (`kernel/auth/summary.py`; three tests). Both are written down in `docs/contracts/auth-api.md`.
  - **Screens:** `kernel/web/src/auth/` (sign-in with every method and the second step, sign-up, forgot password, the seven landings, the step-up dialog, the sign-in frame) and `kernel/web/src/account/` (the security page's five cards and `account.section`, Notifications, Activity). Each kernel screen loads lazily (`app/screens.ts`).
  - **A QR code for the authenticator app's key** (the owner's yes): the kit's `QrCode` on uqr, dark on light in every theme; jsQR reads it back in Vitest and in Playwright.
  - **The kit** gains the site's look (`.mf-site-look`), `Button` `large` and `strong`, `Field` `large` and `aside`, `Card` `description`, the `key` and `mail` icons, `.mf-text-link`.
  - **Two bugs found, each failing first:** a hovered primary button drew `text-strong` words (from #82; `kit.spec.ts`); the frame's Sign out went home without signing out, because React Router draws a move in a transition (`sign-in.spec.ts`; the router now takes `flushSync`, `drawNow` in `mount.tsx`).
  - **The e2e server** is at `http://localhost:<port>` with DEBUG on and rate limits off, so writes and passkeys pass the origin checks.
  - **By eye:** `dev plans/2026-11-19-k45-screens/`, with what differs from the boards.
  - **Review:** Codex's one finding and CodeRabbit's fifteen, then its follow-ups, all fixed with failing-first tests (the PR body lists them): the device list comes in pages (SPEC 7), Sign out from a page with unsaved changes signs out once the person leaves, a sign-in as another account forgets the last one's answers, a landing re-reads the session and offers Try again when it can't.
  - **Tests on the last head:** Vitest 396 passed; Playwright 58 passed (the sign-in spec 18 after the last fixes); Python 2,020 passed at 98.49 % on the first head, the suites the review's server change touched 754 after it, and CI's whole Python job green on the head.
- **v1.0:** 53 % (32 of 60 steps). The ledger is republished.

## Next

1. **K4.6, the admin shell** (contract §4 item 6): the sidebar, the top bar (Ctrl K, notices, View site), the page header, Dashboard and Activity, and `GET /api/kernel/admin/attention`, to the VM Website Admin boards in the admin's look.
2. **Then K4.7 and K4.8.**

## Open questions for the owner

- **The sign-in screens' words:** the board's "Join the vibe" and "Vibrify ya mind" are VM's. A way for a site to reword kernel screens (as mails already can) is unplanned.
- Decisions 0032 to 0039's own calls; the R2 test buckets; the desk steps (the `postgres` password, `Set-ExecutionPolicy`).
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills?
- Carry `line-3` and the four tint aliases back to VM Website's `tokens.json` (that project's session)?
- `C:\DEV\knowledge\owner.md` is uncommitted; the owner commits it.

## Notes

- **React Router draws each move in a transition:** `navigate()` settles before the new page is drawn. Code that reads the drawn location after it asks for `flushSync: true`.
- **A theme switch in a test fades parts with transitions:** wait for `document.getAnimations()` to finish before measuring (kit, parity and sign-in specs do).
- **Traps:** `npx.cmd playwright test -g "..."` with a space breaks its quoting; pick by `file:line`. A pinned count in `tests/test_theme_vibrant_mindz.py` moves with every alias. cubic resolves its own threads; reply anyway. `react-router/dom` under Vitest loads a second copy of React Router: give `RouterProvider` its `flushSync` prop instead.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first.
