# K4's gate: the evidence (2026-11-20)

The gate (contract `dev plans/contracts/k4-web-kernel.md` §7; `docs/progress.json`): component tests, axe with no serious violations, Playwright runs of every sign-in method, and the rest of §7. Checked on `main` at `ca00054` (#88's head, every K4 PR in) on the owner's machine, against the local Postgres 16, on a still tree. The web half was then run again at `03675ac`, after #89.

**Result: passed**, on `main` at `03675ac`. The first run found one real race, a stale People list after a role save (under "The one finding"). The owner chose to fix it before the gate; #89 did, with a test seen failing first, and every check passes on its head. No Python changed between the two heads, so the Python run at `ca00054` stands for both.

## The runs

| Check | Result |
| --- | --- |
| `pytest --cov=kernel` (`MECHFRAME_REQUIRE_DB=1`) | **2,126 passed, 8 skipped, 19 xfailed** in 11 min 53 s; coverage **98.73 %** |
| `npm run test:coverage` at `ca00054` | 39 files, **490 passed**; lines **96.67 %** (statements 94.85, branches 89.70, functions 93.38) |
| `npm run lint`, `typecheck`, `build` | pass |
| `npm run e2e` (Playwright 1.64.1, Chromium) at `ca00054` | **72 passed, 1 failed** in 49.9 s; the failed one passed **5 of 5** alone (`--repeat-each=5`) |
| CI on `main` at `ca00054` | CI (run 44726864696) and E2E (run 44726863784, Linux, the whole suite) both green |
| **At `03675ac`, after #89:** `npm run test:coverage` | 39 files, **491 passed**; lines **96.67 %** |
| At `03675ac`: lint, typecheck, build | pass |
| At `03675ac`: `npm run e2e`, twice | **73 passed** and **73 passed** (56.8 s, 56.4 s) |
| CI on `main` at `03675ac` | E2E (run 44747870263, Linux) green; #89's CI (run 44747056269) green |
| `tools.themes --check`, `tools.openapi --check`, `tools.event_schemas --check`, `tools.progress --check` | all current |

The 8 skips: the 5 live R2 tests (no buckets yet), `test_sigterm_drains_and_exits_0` (Windows; CI runs it on Linux), and two symlink tests Windows can't make. The 19 strict expected failures are K2 steps 9 to 11. Every K4 backend file is at 100 % but `auth/roles.py`, at 95.90 % (branches beside the race locks).

## Each §7 bullet

| Bullet | Evidence |
| --- | --- |
| Committed specs current, every route typed | `tests/test_openapi.py` (20): `test_the_committed_specs_are_current`, `test_every_api_route_declares_a_typed_answer`, `test_routes_build_json_only_through_answer` |
| Contract tests for additions 2 to 9 | Over HTTP. 3: `kernel/tests/contract/test_auth_contract.py` (the device routes, from `test_the_device_list_shows_each_browser_signed_in` to `test_the_device_routes_need_a_session`, paging included). 4 and 5: `test_people_roles_contract.py` (20 tests). 6 to 8: `test_settings_system_contract.py` (28). 2 and 9 are tested over HTTP outside the contract folder, setting their state through the kernel's models: `kernel/tests/test_server_copy.py` (`GET /api/kernel/site`, line 894) and `kernel/tests/test_attention.py` (6) |
| Role editing: each refusal, and a holder's new token | `test_a_permission_you_dont_hold_is_refused` (403 `auth.role_not_yours`), `test_an_unknown_permission_is_refused` (422), `test_an_id_taken_is_refused` (409 `auth.role_exists`), the built-in and in-use refusals (409 `auth.role_builtin`, `auth.role_in_use`, lines 346 to 354), `test_an_unknown_role_isnt_found`, `test_a_role_written_from_another_origin_is_refused`; `test_a_holders_next_request_carries_a_new_token` |
| Kernel pages 200 with noindex; an overlapping module pattern refused | `kernel/tests/test_shell.py`: `test_each_kernel_page_is_the_shell_with_its_title_and_noindex`, `test_a_member_page_is_the_shell_with_noindex_and_no_words`, `test_the_admin_is_the_shell_with_noindex`, `test_a_kernel_page_is_the_kernels_whatever_module_pattern_takes_it` |
| Coverage 95 % or more | 98.73 % |
| Vitest | `api/client.test.tsx`, `session/session.test.tsx`, `guards/next.test.ts`, `slots/slots.test.tsx`, `modules.test.ts` (`defineModule`), `app/pages.test.ts` (pages equal to `kernel.json`'s), `seo/Seo.test.tsx`, the kit's parts (`ui/*.test.tsx`, 15 files), and each screen (`auth/`, `account/`, `admin/`, 14 files); 85 % of lines reached |
| Every sign-in method | `kernel/tests/e2e/sign-in.spec.ts`, "signing in": with a password; then the app's code; then a recovery code made on the account page; a passkey alone, or a password then the passkey; a code by email; a link by email |
| Sign-up and verify, reset, factors and devices | `sign-in.spec.ts`: signing up then confirming from its mail; resetting a forgotten password; the account sets up and removes the authenticator app; signs another device out, and every other |
| A smoke test of each admin page | `admin.spec.ts`: "every admin page answers in the frame" (all seven `/admin` pages) |
| Parity on `/` | `parity.spec.ts`: "the home page says only what the server's copy says" |
| axe on every page in both themes | All 20 pages in `kernel/kernel.json`: the 10 public ones in `parity.spec.ts` (from `KERNEL_PAGES`, with `/` and a 404), the 3 member ones in `sign-in.spec.ts` (a dialog open, the second step, a refusal), the 7 admin ones in `admin.spec.ts` (Settings' three tabs, New role, a person's roles, the notices, Jump to); the kit in `kit.spec.ts`. No serious or critical finding |
| Themes | `tests/test_themes.py` (23), `tests/test_theme_vibrant_mindz.py` (10); no colour literal in `kernel/web/src` |
| By eye | `dev plans/2026-11-19-k45-screens/`, `k46-admin/`, `k47-people-roles/`, `k48-settings-system/`: every auth, account and admin screen at 1440 and 390 px in both themes, beside its board where one was drawn, each folder's README saying what differs and why. Contrast as rendered: the axe runs above, and the kit's 3:1 boundary test. The K4.8 README names no contrast run; its axe test is `admin.spec.ts`'s "in Settings" |

## The one finding

**`admin.spec.ts:182`, "an admin makes a role, gives it to someone, and Roles counts them"**, failed at line 204 in the full run. The handoff had seen it fail once under load. At the failure the page said "Saved …'s roles." while the person's row still showed `Member` and `Off`: the list had been read again before the toast, and the read was stale. The server had committed the grant before it answered (`kernel/auth/roles.py:310`).

The cause, shown by a throwaway script against the installed `@tanstack/query-core` 5.107.1: `invalidateQueries` cancels and refetches a query that has data, but a query still loading its **first** data is handed back that same request. The test types a search and opens the person from the unsearched list before the search settles (300 ms). Under load the search's first page is still on its way when Save lands, and its read began before the commit, so the save's invalidation keeps the old answer. A person who searches, opens someone at once and saves would see the old roles until the next read. The roles themselves are right.

**Fixed by #89** (the owner's call, 2026-11-20): People cancels the people list before it invalidates it, so the refetch starts fresh. `People.test.tsx`'s "are shown as saved when the save lands while a search's first page is on its way (K4's gate)" holds the search's first page until after the save commits. It failed before the fix, the row reading `Off`. No other screen can meet this race: Roles, Features, System, Notices and the account's lists have fixed keys, and their writing controls are drawn from data already loaded. A settings section's history is read on demand, not through the query cache.

## The contract lint on the kernel (`module-contract-lint`)

| Area | Result | Evidence |
| --- | --- | --- |
| Manifest | pass | `python -m tools.validate_schemas`: 17 files, 0 problems |
| Layout | not applicable | the kernel isn't a module; its layout is SPEC 5's |
| Routes declare access | pass | `undeclared(app) == []` on `create_app` (also `kernel/tests/test_app.py`); 71 `/api` routes, the 25 admin ones all under `/api/kernel/admin` or `/api/auth/admin`; the lists the contract pages are tested in pages (devices, people, settings history, failed jobs, both activity logs) |
| Errors | pass | problems throughout; the one `HTTPException` (`errors.py:213`, a body over the limit as it streams) is deliberate and answered as problem details by `_http` |
| Boundaries | pass | no import of `modules` or `harness` from `kernel/backend` |
| Data and security | pass | no `dict` bodies in the kernel's routes |
| Front end | pass | no colour literal in `kernel/web/src`; lint, typecheck and Vitest as above |
| Quality gate | pass | ruff; black (237 files); mypy strict (156 files); coverage as above |
| Secrets and dependencies | pass | gitleaks over 218 commits: none; pip-audit: none; `tools.npm_audit`: no advisories, allowed or not; the brand check: clean |
