# Handoff

Overwritten every session. This one: 2026-11-18, night, to 2026-11-19, early morning Eastern (Claude Code, the owner's machine). #81 had already landed. K4.4, the UI kit, is #82, and this page rides in it.

## State

- **K0 to K3 are done.** K2 steps 9 to 11 wait (decision 0029). The device list's three routes (K2 step 4) were never built and have no contract tests yet: K4.5 writes those tests first.
- **K4** (contract `dev plans/contracts/k4-web-kernel.md`, decision 0042): four of its eight PRs are in.
  - #78, the typed client. #79, the app shell. #80, the themes.
  - **#82, the UI kit** (contract change 15):
    - **The parts:** `kernel/web/src/ui/`, exported from `@/kernel`, listed in its `README.md`. `RouteFocus` and `ErrorBoundary` moved there from `app/`. `ScrollMemory` replaces `<ScrollRestoration>`. `IconName` is the kit's 26 icons.
    - **Focus, two ways:** the admin's ring inside `.mf-admin-look`, which the admin frame carries. The site, sign-in and account screens keep the outline.
    - **New required tokens:** `color.border-control` (fields, selects and switch tracks at 3:1), four pill tints, and five focus shadows. Vibrant Mindz gained one value, `line-3` `#5C6584`.
    - **The owner chose** the 3:1 field edge and the dark knob on an on switch (2026-11-19, 02:15 Eastern).
    - **The kit's page:** the harness builds `/kit.html`. `kernel/tests/e2e/kit.spec.ts` checks it in both themes: axe, each control's boundary as drawn, the focus rings with real Tab presses, the Table's `focusin` scroll at 390px, and the SaveBar's room.
    - **Fixed on the way:** a Sign out race in the frame. A failing test came first.
    - **Review:** Codex's first round found two slips, both fixed with failing-first tests: a new `#place` on the same page, and a toast held by the pointer and the keyboard apart.
- **Tests on e033438, locally:**
  - Python: 1,994 passed, coverage 98.53 %.
  - Vitest: 249 passed, 98.22 % of lines.
  - Playwright: 38 passed.
- **v1.0:** 52 % (31 of 60 steps) once #82 lands.

## Next

1. **Land #82** if it's still open. Answer the bots' threads, with a failing test first where a fix touches code. Land by fast-forward once "CI result" is green and no thread is open. Then republish the ledger (`dev plans/progress-ledger/README.md`).
2. **K4.5, the auth and account screens** (contract §4 item 5), built to `Auth.dc.html` and `Account.dc.html` in VM Website `design/site/`.
   - **Order:** write the device routes' contract tests first and see them fail (`docs/contracts/auth-api.md`'s `GET /api/auth/sessions`, `DELETE /api/auth/sessions/{id}` and `POST /api/auth/sessions/sign-out-others`), then build the routes, then the screens.
   - **The step-up dialog** is the kit's `Dialog`. `api` already retries a write once after a step-up; it needs the dialog's hook.
   - **Site-look sizes:** buttons and fields are 54px, buttons fully round, fields at a 14px radius (shell-slots.md, finding 3 and "Sign-in"). Add them as `Button` and `Field` sizes; don't build a second kit.
   - **Tests:** `kernel/tests/e2e/sign-in.spec.ts`, covering every sign-in method, sign-up and verify, reset, and the account's factors and devices. The sign-in and account pages join the axe run.
3. **Then K4.6 to K4.8.**

## Open questions for the owner

- Decisions 0032 to 0039's own calls: keep them?
- When to make the R2 test buckets. The desk steps: the `postgres` password, and `Set-ExecutionPolicy` if wanted.
- Rename `C:\DEV\AI-DevKit` and the account's `devkit-*` skills?
- Carry `line-3` and the four tint aliases back to VM Website's `tokens.json` (that project's session)?
- `C:\DEV\knowledge\owner.md` is uncommitted; the owner commits it.

## Notes

- **Measure a control's boundary as drawn,** composited over what's behind it. A token pair can't see a fill over a fill. Mutants are how `kit.spec.ts`'s Table and SaveBar tests were shown to catch what they guard.
- **jsdom** has no `showModal`, `scrollIntoView` or `scrollTo`. `vitest.setup.ts` gives the first two as browsers behave and makes `scrollTo` do nothing.
- **Traps:**
  - `npx.cmd playwright test -g "..."` with a space breaks its quoting. Pick the test by `file:line`.
  - A pinned count in `tests/test_theme_vibrant_mindz.py` moves with every alias or role added.
  - cubic resolves its own threads: post the reply anyway.

## Warnings

- Nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- Editing CI's security gates is the owner's call: ask first.
