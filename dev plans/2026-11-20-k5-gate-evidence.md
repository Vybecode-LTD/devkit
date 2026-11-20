# K5's gate, and the kernel's close: the evidence (2026-11-20)

K5's gate (KICKOFF K5; contract `dev plans/contracts/k5-cli-and-site-template.md` §7): in a temporary folder, `mechframe new test-site` with the kernel only builds, migrates and passes its tests, and `mechframe check` passes on it. Then KICKOFF's "The kernel is done when". Checked on `main` at `b543642` (#95's head, every K5 PR in), on the owner's machine against the local Postgres 16, on a still tree, from 6:40 to 6:55 PM Eastern (23:40 to 23:55 UTC).

**Result: K5's gate passed.** No finding. The kernel's close is in its own section below. Every one of its rows passes, with one gap found for the first module (MODULE.md's sections) and K2's steps 9 to 11 still waiting, as decision 0029 says.

## The runs

| Check | Result |
| --- | --- |
| `python -m tools.site_smoke --keep` (local, `TEST_DATABASE_URL` on port 55432) | **every step passed**, 26 in all, in about 6 minutes, 164 s of it pip. The site was kept in `%TEMP%\mechframe-smoke-nm99466y\test-site` and is not in the repo |
| The kernel-only pass | venv; `pip install --require-hashes`; ruff, black, mypy; migrations; pytest **15 passed** (`MECHFRAME_REQUIRE_DB=1`, none skipped); `npm ci`; ESLint, tsc; Vitest **3 passed**; the Vite build; `npm ci` for Railway's SDK and `railway.ts` held to its types; Playwright **4 passed**; `mechframe check`: kernel `0.1.0-dev.0`, none edited, missing, added or behind, **exit 0** |
| The pass with modules (`mechframe add fixture-notes fixture-pins`) | ruff, black, mypy; migrations; pytest **15 passed**; ESLint, tsc; Vitest **3 passed**; the build; `mechframe check`: the kernel and both fixture modules, none edited, missing, added or behind, **exit 0** |
| `npm audit` in the new site, its root (Railway's SDK) and `web/` | 0 vulnerabilities in each. The repo's `tools.npm_audit` doesn't reach the site's root lockfile, so this ran by hand |
| CI on `main` at `b543642` (run 44838517622) | Python 3.12 and 3.13: **2,374 passed, 5 skipped, 19 xfailed**, coverage **98.16 %**; Web: Vitest **511 passed** in 40 files, lines **96.69 %**; lint, typecheck, `api:check`, build; gitleaks over 240 commits, pip-audit and `tools.npm_audit` clean |
| E2E on `main` at `b543642` (run 44838517723, Linux) | Playwright **73 passed**; the `site-smoke` job: every step passed, alone and with modules |
| Local, at `b543642` | gitleaks over 240 commits: none; pip-audit: none; `tools.npm_audit`: no advisories, allowed or not; VybeSite's brand check: clean |

The 5 skips in CI are the live R2 tests (no buckets yet). The 19 strict expected failures are K2 steps 9 to 11 (decision 0029).

## Each §7 bullet

| Bullet | Evidence |
| --- | --- |
| `cli/tests/`: each command's refusals and exit codes | `test_cli.py` `test_a_command_not_built_yet_is_refused`; `test_reports.py` `test_a_refused_check_prints_why_and_exits_2`; `test_check.py` `test_an_open_high_advisory_fails_the_check` (exit 1) and `test_an_unedited_site_is_clean` (exit 0); `test_new.py`'s refusals (a folder not empty, an unknown theme, a name that can't be a site's, a checkout without the template); `test_add_remove.py`'s 12 refusals; `test_recipe.py`'s 5; `test_create_owner.py` (it answers the site's own exit; no venv, not a site) |
| The lock validates and round-trips | `lock.read` and `lock.write` both hold it to `schema/lock.schema.json` (`cli/mechframe/lock.py`): `test_a_missing_or_invalid_lock_is_refused`, `test_a_lock_that_doesnt_validate_isnt_written`, `test_a_lock_that_isn_t_json_is_refused`, `test_the_lock_s_schema_refuses_a_version_semver_refuses`. Round trip: `test_check_names_a_copy_behind_the_checkout` reads, writes and checks a lock again; `test_a_new_site_holds_the_template_the_kernel_and_its_lock` |
| A CRLF checkout of an unedited copy reads as unedited | `test_a_checkout_with_windows_line_endings_reads_as_unedited`, `test_a_file_s_hash_ignores_the_line_endings_git_writes`; `test_a_crlf_site_keeps_its_line_endings` for `add` |
| `check` names an edited, a missing and an added file, and a version behind; fails on a high advisory only | `test_check_names_an_edited_a_missing_and_an_added_file`, `test_check_names_a_copy_behind_the_checkout`, `test_an_open_high_advisory_fails_the_check`, `test_a_low_advisory_is_named_but_passes`, `test_only_advisories_for_the_site_s_own_versions_are_open` |
| `catalog --check` catches a stale file | `test_check_finds_a_stale_catalog_and_leaves_it_alone`, `test_a_missing_catalog_is_stale`; `test_the_repo_s_catalog_is_current` |
| `add` refuses a conflict and a missing requirement; `remove` refuses while another module requires its module | `test_add_refuses_a_conflict_either_way`, `test_add_refuses_a_missing_requirement_and_names_it`, `test_remove_refuses_while_another_module_needs_it` |
| The registries `add` writes import and build | `test_registries.py` (4); `tests/test_site_template.py` `test_a_site_with_modules_imports_each_binding_it_lists` and `test_a_site_with_modules_is_linted_clean_and_passes_its_tests`; the smoke's second pass (mypy, tsc, Vitest and the build with modules) |
| `tests/test_site_template.py` | The web dependencies equal the root's: `test_the_web_dependencies_are_mechframes`, `test_the_web_lockfile_holds_the_same_versions`. Every file in the table: `test_every_file_the_contract_lists_is_there`. `CLIENT_IP_HEADER`: `test_the_environment_names_every_setting_and_a_real_client_address`. `--proxy-headers`: `test_the_start_command_reads_the_proxys_headers`; `FORWARDED_ALLOW_IPS=*` on Railway: `test_railway_builds_the_dockerfile_migrates_first_and_trusts_its_edge` |
| The site's own tests, run by the smoke in the new site | `test_app.py` `test_the_app_builds_and_every_route_declares_its_access` (`undeclared(app) == []`); `test_migrations.py` `test_upgrade_downgrade_upgrade`, on an empty database; `test_pages.py` `/`, `/sign-in` and a 404 (`test_the_home_page_is_the_sites_own_with_its_words`, `test_sign_in_is_the_shell_titled_and_not_indexed`, `test_an_address_the_site_doesnt_have_is_a_real_404`); Vitest `src/site/Home.test.tsx` (3); Playwright `e2e/smoke.spec.ts`: `/` and `/sign-in` with nothing serious for axe, the home page's parity with its server copy, and a real 404 |
| The gate | The smoke, above: `mechframe new test-site` (kernel only) installs, builds, migrates and passes its tests, and `mechframe check` exits 0, here and in main's E2E |

## The kernel's close (KICKOFF, "The kernel is done when")

**Every row of SPEC 16 passes for the kernel, in CI**, on `main` at `b543642`:

| Row | Where CI runs it | Result |
| --- | --- | --- |
| Backend tests | CI's Python job: `pytest --cov --cov-fail-under=85`, on 3.12 and 3.13 | 2,374 passed; 98.16 % |
| Contract tests | `kernel/tests/contract/` over HTTP (auth, people and roles, settings and System, the route audit), in the same run | pass; 19 strict xfails for K2 9 to 11 |
| Migrations | `tests/test_migrations.py` `test_upgrade_downgrade_upgrade` and `..._with_a_row_in_every_table` | pass |
| Front end | CI's Web job: Vitest with the 85 % floor | 511 passed; 96.69 % of lines |
| End to end | E2E (main's pushes, weekly, by hand; never a PR, decision 0015) | 73 passed |
| Types and lint | ruff, Black, mypy strict, `tsc`, `eslint --max-warnings=0` | pass |
| Accessibility | axe in the E2E suite on all 20 of `kernel/kernel.json`'s pages in both themes (K4's gate evidence) | nothing serious or critical |
| Public pages | `parity.spec.ts`; `kernel/tests/test_shell.py` and `test_server_copy.py` (the head, canonical, JSON-LD) | pass |
| Security | the auth contract tests; gitleaks; pip-audit; `tools.npm_audit` | clean |
| Tokens | ESLint's colour rule; `tests/test_themes.py`, `tests/test_theme_vibrant_mindz.py` | pass |
| Docs | `tools.validate_schemas` (`kernel/kernel.json`, the schemas, the fixtures) | pass |

**The auth contract tests pass:** every 14.13 test for steps 1 to 8 passes. The 19 for OAuth, invites and API keys, and abuse protection, deletion and export are strict expected failures until K2's steps 9 to 11 are built where the site needs them (decision 0029). That's why K2's `gate_passed` stays false.

**The brand check, gitleaks, pip-audit and npm audit are clean** (the runs, above).

**The docs are current.** `CLAUDE.md`'s commands gain `create-owner` in this PR. The decision records run to 0051, each "Decided; applied", with the index current. `docs/HANDOFF.md` and the current state are rewritten at this session's end.

**One gap, for the first module, not the kernel.** SPEC 16's Docs row says `mechframe check` finds a `MODULE.md` missing a required section (SPEC 17 lists them). Nothing checks that yet: `check` validates a copied `module.json`, but no module has a `MODULE.md` to read. It belongs with wave 1's first module, in `check` and `module-contract-lint`.

### The spec sections that changed since K0

Spec v0.1, with the owner's answers, was the contract K0 started from (2026-11-12). SPEC's change log has each change since then with its decision. By section:

| Section | What changed (decisions) |
| --- | --- |
| Header | The one copy of the spec; the claude.ai doc retired (0017) |
| Every section | Renamed MechFrame (0034) |
| 2. The stack | The jobs worker in the web process; SMTP first, Resend where SMTP is blocked (0033, 0035) |
| 4. Layout | The module layout is the template's (0016); email's files (0033); the committed OpenAPI specs (0042); the CLI, a site's exact layout, `.railway/railway.ts` (0047, 0048) |
| 5. Manifest | `settings` defers to the `Settings` model; `notifications` (0009, 0016) |
| 6. Kernel API | Storage, email, jobs, events, audit, notifications, moderation, public rendering, the typed client, the admin's routes, `load_module`, the site's pages (0009, 0016, 0031 to 0033, 0035 to 0039, 0041, 0042, 0044, 0048) |
| 7. Backend rules | Discovery names, problems, secrets; `Answer` models (0009, 0016, 0033, 0039, 0041, 0042) |
| 8. Frontend and slots | The app shell, themes and tokens, the UI kit, the sign-in and admin frames, the site's own pages (0040, 0042 to 0044, 0048) |
| 9. Public rendering | Server copy, the shell, real 404s, `sitemap.xml`, `robots.txt`, `llms.txt`; the parity test; the site's pages (0041, 0042, 0048) |
| 10. Data and migrations | A destructive migration waits for the owner (0049) |
| 11. Events | The kernel's events, moderation's, the module switches', `auth.user.role_changed` (0036, 0039, 0045, 0046) |
| 12. Module lifecycle | Switches cached; switches audited; `add` prints its steps; `add`, `remove`, `new --recipe` (0009, 0046, 0047, 0050) |
| 13. Versioning and the lock | Lock hashes, `advisories.json`, `check`'s exits (0047) |
| 14. Auth | 14.1 to 14.13 throughout: sign-up, codes and links, resets, email change, passwords, TOTP, passkeys, the undo link, roles and role editing, unverified accounts removed, the audit log, notices, moderation's suspension, and `create-owner` in place of the setup token (0010, 0012 to 0014, 0019 to 0028, 0030, 0031, 0035, 0037 to 0039, 0043 to 0046, 0051) |
| 15. Security | The CSP directives a module may open; storage's rules (0016, 0032) |
| 16. Quality gate | When CI runs; npm audit's expiring allowlist; the colour rule; the kit's tokens (0015, 0042) |
| 17. The AI layer | The catalog's fields (0047) |
| 18. Platform bindings | The committed OpenAPI as the contract (0042) |
| 20. Owner answers | The admin built to the canvas design (0040) |

Sections 1, 3 and 19 changed only by the rename.
