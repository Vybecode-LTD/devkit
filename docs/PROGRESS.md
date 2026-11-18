# MechFrame progress

Generated from `docs/progress.json` by `python -m tools.progress`: edit the JSON, then run the tool. `tests/test_progress.py` fails when this page is stale. The same data feeds the [visual progress ledger](https://claude.ai/artifact/48auLkb7Ajmyn2SNAni9rm).

Updated 2026-11-18, `main` at `c38cdfa`. Progress counts steps, not effort: each row below is one step, whatever its size.

## Overall

| Milestone | Done | In review | Next | To do | Waiting | Later | Progress |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| MechFrame v1.0 | 27 | 1 | 1 | 25 | 3 | 3 | ████░░░░░░ 45% (27 of 60) |
| After v1.0 | 0 | 0 | 0 | 85 | 0 | 3 | ░░░░░░░░░░ 0% (0 of 88) |
| Everything | 27 | 1 | 1 | 110 | 3 | 6 | █░░░░░░░░░ 18% (27 of 148) |

## MechFrame v1.0

The kernel, the CLI and the first validation modules, frozen once blog, chat and payments pass the quality gate on the Vibrant Mindz build (SPEC 19).

### Spec v0.1 · 1 of 1 done

The contract every module, the kernel and the CLI follow.

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| Spec v0.1 written, the owner's answers applied | Done |  | [0001](decisions/0001-backend-python-fastapi.md), [0002](decisions/0002-copy-in-modules.md), [0003](decisions/0003-homemade-auth.md) |  |

### K0: repo foundation · 3 of 3 done · gate passed

Python, the harness, Alembic, the web workspace and CI.

Gate: pytest, npm test and the schema checks pass; CI green.

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| Python environment, harness, Alembic, web workspace, CI | Done |  |  |  |
| The audit's fixes and the review bots' follow-ups | Done |  |  | PRs #1 to #24 |
| The owner's follow-ups: history rewrite, ruleset on main, pinned actions | Done |  |  | PRs #25 to #31 |

### K1: kernel core · 3 of 3 done · gate passed

The database, settings, module switches, crypto, errors, rate limits, access marks and the app factory.

Gate: Tests for each piece, secret refusal, CSP headers, a switched-off module answering 404, the migration round trip.

Done: `Database, settings and module switches`, `Crypto, errors, rate limits and access marks`, `The app factory, security headers and CSP`.

### K2: auth · 8 of 11 done · gate not passed yet

The complete auth system of SPEC 14, test-first.

Gate: Every 14.13 contract test passes; each sign-in method works by hand; brand check, gitleaks and pip-audit clean.

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| 1. The contract suite, written first | Done |  |  | 128 pass; 27 wait on steps 9 to 11 |
| 2. Accounts, roles and per-resource overrides | Done | [#36](https://github.com/mechframe/mechframe/pull/36), [#56](https://github.com/mechframe/mechframe/pull/56) | [0031](decisions/0031-moderation-permission.md) |  |
| 3. Passwords | Done | [#7](https://github.com/mechframe/mechframe/pull/7), [#10](https://github.com/mechframe/mechframe/pull/10) |  |  |
| 4. Sessions | Done | [#32](https://github.com/mechframe/mechframe/pull/32), [#33](https://github.com/mechframe/mechframe/pull/33) |  | The device list's three routes were never built, and no contract test calls them (found 2026-11-18): they moved to K4's step "Auth and account screens, with the device routes" |
| 5. Sign-in codes and magic links | Done | [#42](https://github.com/mechframe/mechframe/pull/42) | [0021](decisions/0021-codes-and-links.md) |  |
| 6. Reset, verification and email change | Done | [#39](https://github.com/mechframe/mechframe/pull/39), [#43](https://github.com/mechframe/mechframe/pull/43), [#44](https://github.com/mechframe/mechframe/pull/44), [#45](https://github.com/mechframe/mechframe/pull/45), [#46](https://github.com/mechframe/mechframe/pull/46) | [0020](decisions/0020-sign-up-defaults.md), [0022](decisions/0022-password-resets.md), [0023](decisions/0023-verification-resend.md), [0024](decisions/0024-email-change.md), [0025](decisions/0025-password-change.md) |  |
| 7. Second factors and step-up | Done | [#38](https://github.com/mechframe/mechframe/pull/38), [#47](https://github.com/mechframe/mechframe/pull/47), [#48](https://github.com/mechframe/mechframe/pull/48), [#52](https://github.com/mechframe/mechframe/pull/52) | [0019](decisions/0019-sign-in-limits-as-tiers.md), [0026](decisions/0026-totp-setup-and-confirm.md), [0027](decisions/0027-totp-removal-and-recovery-codes.md) |  |
| 8. Passkeys, and the undo link for an added factor | Done | [#50](https://github.com/mechframe/mechframe/pull/50), [#54](https://github.com/mechframe/mechframe/pull/54) | [0028](decisions/0028-passkeys.md), [0030](decisions/0030-second-factor-undo.md) |  |
| 9. OAuth and OpenID Connect | Waiting |  |  | Before the site's launch at step 5 |
| 10. Invites and API keys | Waiting |  |  | Invites before the site's step 4; API keys after |
| 11. Abuse protection, deletion and data export | Waiting |  |  | Before the site's launch at step 5 |

### K3: kernel services · 9 of 11 done · gate passed

Everything else modules rely on, in the order the site's modules use it.

Gate: Tests for each service; an event delivered once to a handler safe to run twice; a job surviving a worker restart. Checked on the nine services built; retention and the AI client are outside it (the owner, 2026-11-17).

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| Storage | Done | [#58](https://github.com/mechframe/mechframe/pull/58) | [0032](decisions/0032-kernel-storage.md) |  |
| Email: templates, SMTP first, Resend where SMTP is blocked | Done | [#59](https://github.com/mechframe/mechframe/pull/59) | [0033](decisions/0033-kernel-email.md) |  |
| The kernel's own mails as templates a site can reword | Done | [#60](https://github.com/mechframe/mechframe/pull/60) | [0033](decisions/0033-kernel-email.md) |  |
| Jobs: the Postgres queue, the scheduler, mail retries | Done | [#63](https://github.com/mechframe/mechframe/pull/63) | [0035](decisions/0035-kernel-jobs.md) |  |
| Events: emitted in the caller's transaction, delivered as jobs, dead letters | Done | [#65](https://github.com/mechframe/mechframe/pull/65) | [0036](decisions/0036-kernel-events.md) |  |
| Audit: one append-only log for every module, auth's widened | Done | [#67](https://github.com/mechframe/mechframe/pull/67) | [0037](decisions/0037-kernel-audit.md) |  |
| Notifications, with per-person preferences and one-click unsubscribe | Done | [#69](https://github.com/mechframe/mechframe/pull/69) | [0038](decisions/0038-kernel-notifications.md) |  |
| Moderation: reports, the staff queue, filters and actions | Done | [#56](https://github.com/mechframe/mechframe/pull/56), [#71](https://github.com/mechframe/mechframe/pull/71) | [0031](decisions/0031-moderation-permission.md), [0039](decisions/0039-kernel-moderation.md) |  |
| Public rendering: head tags, server copy, sitemap, robots, llms.txt | Done | [#73](https://github.com/mechframe/mechframe/pull/73) | [0041](decisions/0041-public-rendering.md) |  |
| Retention | Later |  |  | Outside K3's gate (the owner, 2026-11-17); its tests come with it |
| The AI client | Later |  |  | Outside K3's gate (the owner, 2026-11-17); its tests come with it |

### Rename to MechFrame · 2 of 2 done

AI DevKit became MechFrame once K3 was done (decision 0034).

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| One PR: prose, packages, cookies, variables, skills and links say MechFrame | Done | [#76](https://github.com/mechframe/mechframe/pull/76) | [0034](decisions/0034-rename-to-mechframe.md) |  |
| The owner moves the repo to github.com/mechframe/mechframe and installs the review bots there | Done |  | [0034](decisions/0034-rename-to-mechframe.md) | 2026-11-18: transferred; Codex, CodeRabbit and cubic review there |

### K4: web kernel · 0 of 9 done · gate not passed yet

The front-end half of the kernel.

Gate: Component tests, axe with no serious violations, Playwright runs of every sign-in method.

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| The typed client: every answer typed, the committed specs, api and its hooks | In review | [#78](https://github.com/mechframe/mechframe/pull/78) | [0042](decisions/0042-web-kernel.md) |  |
| The app shell: router, useSession, guards, slots, the kernel's pages, server copy, Playwright | Next |  |  |  |
| Themes: Machined Light and Vibrant Mindz on the kernel's tokens | To do |  |  |  |
| UI kit, moved to React 19 and tokens | To do |  |  |  |
| Auth and account screens, with the device routes | To do |  |  |  |
| Admin shell: sidebar, top bar, Dashboard and Activity | To do |  |  |  |
| Admin people and roles, with role editing | To do |  |  |  |
| Admin settings: Site, Features and System | To do |  |  |  |
| Depth theme | Later |  |  | The owner, 2026-11-18: when a site wants it |

### K5: CLI and site template · 0 of 4 done · gate not passed yet

mechframe works end to end.

Gate: mechframe new test-site builds, migrates and passes its tests; mechframe check passes on it.

To do: `The mechframe commands and lock files`, `templates/site, made from the harness`, `The start command and .env.example for a host's edge`, `mechframe catalog`.

### Contract hooks · 0 of 10 done

The ten hooks the Must modules need, before blog, chat and payments are extracted (decision 0018).

To do: `Search index`, `Consent categories`, `Entitlements`, `Bot check`, `Export and erase`, `Content lifecycle`, `Taxonomy`, `Profile tabs`, `Dashboard cards`, `Seed data`.

### Vibrant Mindz site, to launch · 1 of 6 done · gate not passed yet

The first real site, built from the modules; it doubles as the spec's validation (docs/plans/vibrant-mindz-backend/KICKOFF.md).

Gate: v1.0 is frozen when blog, chat (community) and payments pass the quality gate.

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| Step 0: scaffold, moderation permission, custom roles | Done | [#55](https://github.com/mechframe/mechframe/pull/55), [#56](https://github.com/mechframe/mechframe/pull/56) | [0029](decisions/0029-vibrant-mindz-order.md), [0031](decisions/0031-moderation-permission.md) |  |
| Step 1: media, pages, blog, embeds, contact, campaigns | To do |  |  |  |
| Step 2: discography, audio player, featured | To do |  |  |  |
| Step 3: roster, portfolio, reactions, comments | To do |  |  |  |
| Step 4: community | To do |  |  |  |
| Step 5: payments, shop, downloads; the v1.0 gate and the site's launch | To do |  |  |  |

## After v1.0

The rest of the Vibrant Mindz site, the module waves, the framework tools and the TypeScript port study (decision 0018, SPEC 19).

### Vibrant Mindz site, after launch · 0 of 2 done

The beat store and the apparel designer.

To do: `Step 6: licensing, the beat store`, `Step 7: print on demand, the apparel designer`.

### Wave 1: foundations every site uses · 0 of 16 done

docs/plans/module-roadmap.md

To do: `forms`, `bot-shield`, `consent`, `analytics-adapters`, `privacy-center`, `legal`, `security-center`, `account-center`, `site-search`, `redirects`, `data-grid`, `import-export`, `command-palette`, `setup-wizard`, `image-pipeline`, `ai-gateway`.

### Wave 2a: sell more · 0 of 8 done

docs/plans/module-roadmap.md

To do: `memberships`, `credits`, `discounts`, `drops`, `tips`, `shipping`, `pricing-table`, `waitlist`.

### Wave 2b: fans and community · 0 of 11 done

docs/plans/module-roadmap.md

To do: `profiles`, `follows`, `feed`, `groups`, `polls`, `bookmarks`, `reviews`, `submissions`, `contests`, `live`, `rooms`.

### Wave 2c: music and media · 0 of 8 done

docs/plans/module-roadmap.md

To do: `video`, `radio`, `podcast`, `music-import`, `press-kit`, `short-links`, `social-feeds`, `transfer`.

### Wave 3a: agency handoff · 0 of 11 done

docs/plans/module-roadmap.md

To do: `migrate`, `invoices`, `client-portal`, `white-label`, `onboarding-tours`, `crm`, `reports`, `email-builder`, `announcements`, `editorial-calendar`, `zapier`.

### Wave 3b: service businesses · 0 of 7 done

docs/plans/module-roadmap.md

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| maps | To do |  |  |  |
| booking | To do |  |  |  |
| events | To do |  |  |  |
| directory | To do |  |  |  |
| recipes | To do |  |  |  |
| google-business | To do |  |  |  |
| sms | To do |  |  | Provider chosen at this wave |

### Wave 4: software products · 0 of 13 done

docs/plans/module-roadmap.md

To do: `license-keys`, `release-channels`, `beta-program`, `crash-reports`, `preset-exchange`, `docs`, `faq`, `changelog`, `wiki`, `helpdesk`, `public-api`, `orgs`, `enterprise-sso`.

### Wave 5: AI layer · 0 of 5 done

docs/plans/module-roadmap.md

To do: `semantic-search`, `concierge`, `agent-ready`, `prompts`, `ai-studio`.

### Framework tools · 0 of 4 done

When each lands is in docs/plans/module-roadmap.md.

| Step | Status | PRs | Decisions | Note |
| --- | --- | --- | --- | --- |
| provenance-scan and quality-gate | To do |  |  | During v1 extraction |
| visual-regression and catalog-site | To do |  |  | After wave 1 |
| theme-generator and fleet | To do |  |  | Wave 3a |
| platform-bridge | To do |  |  | After wave 5 |

### TypeScript port study · 0 of 3 done

After the first real site ships (SPEC 19).

Later: `Port one small module to a TypeScript backend, judged by the same contract tests`, `Measure the effort and what the contract tests caught`, `Record the call in a decision`.
