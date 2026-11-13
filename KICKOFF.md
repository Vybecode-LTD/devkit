# KICKOFF: AI DevKit, phases K0 to K5 (the kernel)

**For Claude Code, run from `C:\DEV\AI-DevKit`.** To start: "Read KICKOFF.md and begin phase K0." Each phase is one or more pull requests, and each ends at its gate. Work the phases in order, one session at a time, and stop at each gate to report.

## What this is

AI DevKit is a library of reusable website modules that any AI agent copies into a site's repo and wires together from a short brief. `SPEC.md` is the contract. This kickoff builds the **kernel**: the core every module depends on. Most of it is lifted from VybeSite (`C:\DEV\VybeSite\vybesite\`), with OAuth from Basefra.me and a few patterns from VybeMindz. The first real site built on DevKit is the new Vibrant Mindz site; its plan is `docs/plans/vibrant-mindz-module-plan.md`.

## Read first, in this order

1. `CLAUDE.md`. (`C:\DEV\CLAUDE.md` and `C:\DEV\DIRECTIVES.md` load on their own.)
2. `SPEC.md`, all of it, once. Re-read the sections a task touches before starting it.
3. `docs/decisions/` (0001 to 0008).
4. `docs/private/inventory.md` (on the owner's machine, not in git), section 4.1: where each kernel piece lives today.
5. `skills/devkit-module-extractor/SKILL.md`. Its steps (choose the source, provenance gate, inventory, cut dependencies) apply to lifting kernel code too.

## Ground rules for every phase

- **Provenance.** Nothing from the client folder named in `docs/private/README.md` or any client-confidential material, ever. Never copy from VybeSite's `dev plans\` or `snapshots\`; they name a past client. Run VybeSite's brand check on every PR that lifts code: `python -I "C:\DEV\VybeSite\vybesite\scripts\brand_check.py" "C:\DEV\AI-DevKit"`.
- **Port behavior, not shape.** Before lifting a piece, read its tests, its docstrings and VybeSite's `CLAUDE.md` notes on it. Where the spec differs from VybeSite (sessions, account tables, module switches), the spec wins.
- **Ask the owner first** before anything outward-facing: creating the GitHub repo, pushing to it the first time, changing its settings, Railway, DNS, or any third-party account. Never type, paste or log a secret.
- **Tests first.** Auth starts from the contract tests in SPEC.md 14.13, seen failing. Every bug fix gets a test seen failing before the fix.
- **One logical change per PR,** on its own branch, with conventional commits. Read the staged diff for secrets before each commit. Auth PRs get the full review: tests, a migration round trip, a live check in the harness, then a self-review against SPEC.md section 14.
- **Second failed fix for the same symptom: stop** and follow `C:\DEV\DEBUG_PROTOCOL.md`.
- **Spec changes** need a decision record, a change-log line in `SPEC.md`, and a note to the owner of which sections to sync into the design doc.
- **Skills:** don't build new skills. Add any idea to `docs/SKILL-BACKLOG.md` with the date and whether it blocks anything.
- **Windows:** the owner's terminal is PowerShell. Python commands use `python -m ...`.

## K0: repo foundation

**Goal:** an empty but fully tooled repo whose CI is green.

1. `git init` on `main`, then commit the scaffold as it is: `chore: scaffold from spec v0.1`.
2. Link the project skills so Claude Code loads them: for each folder in `skills\`, make a directory junction at `.claude\skills\<name>` (PowerShell: `New-Item -ItemType Junction -Path .claude\skills\<name> -Target skills\<name>`), the same pattern as `C:\DEV\knowledge\skills\link_skills.py`. Commit `skills\`, not the junctions.
3. The repo `Vybecode-LTD/devkit` exists and is public (decision 0011): nothing private is ever committed.
4. **Python.** A root `pyproject.toml` for the dev environment. `requirements.in` compiled to a hash-pinned `requirements.txt` with `uv pip compile --generate-hashes`, following VybeSite's `backend/requirements.in` (floors above known vulnerabilities, a comment per package). Dev tools: ruff, Black, mypy (strict for `kernel/`), pytest, pytest-asyncio, httpx, jsonschema.
5. **The harness.** `harness/` is a small FastAPI app that mounts the kernel and any modules in this repo. Tests and local runs use it, and K5 turns it into `templates/site/`.
6. **Postgres for tests.** A `compose.yaml` with Postgres 16, and a pytest fixture that gives each test run a throwaway database.
7. **Alembic.** One environment in `harness/alembic/`, with `version_locations` covering `kernel/migrations` and every `modules/*/migrations`. The kernel's branch is labelled `kernel`; each module's branch depends on the kernel's head. Add a round-trip test (upgrade, downgrade, upgrade).
8. **Web.** A root `package.json` with npm workspaces (`kernel/web`, `modules/*/web`, `harness/web`), `.npmrc` with `ignore-scripts=true`, TypeScript strict, ESLint with zero warnings, Vitest with React Testing Library, and Playwright. React 19, Vite, React Router 7 in library mode, TanStack Query.
9. **Schema checks.** `tools/validate_schemas.py` validates every `module.json`, recipe and `kernel/kernel.json` against `schema/`, with a pytest test that runs it.
10. **CI.** One GitHub Actions workflow whose final job is named `CI result`: lint, types, backend tests (with a Postgres service), web tests, schema checks, gitleaks and pip-audit. Use path filters so a docs-only PR spends no minutes on the test jobs. The brand check runs locally, since CI can't reach `C:\DEV\VybeSite`.
11. Fill in "Commands" in `CLAUDE.md` and `AGENTS.md`.

**Gate:** `python -m pytest`, `npm test` and the schema checks pass locally, and CI is green on the K0 PR (or locally, if the repo isn't created yet).

## K1: core infrastructure

**Goal:** the kernel's non-auth foundations, lifted from VybeSite.

| Kernel piece | Lift from (`C:\DEV\VybeSite\vybesite\backend\app\`) | Notes |
| --- | --- | --- |
| Settings | `core/config.py` | pydantic-settings. Refuse to start outside debug on a default, placeholder or short secret. `MODULES` replaces `PARTS` |
| Database | `core/database.py`, `models/base.py` | Async engine and session, `get_db`, the one-row helper |
| Crypto | `core/crypto.py`, `services/stored_credentials.py` | MultiFernet so keys rotate without downtime |
| Errors | New | RFC 9457 problem details with a stable `code`; exception handlers |
| Security middleware | `middleware/security_headers.py`, `same_origin.py`, `www_redirect.py` | Strict CSP with no inline script or style, plus a hook for modules to add hosts only while switched on |
| Rate limiting | `core/ratelimit.py` | Keys per IP and per account behind an interface Redis can back later |
| Error tracking and logs | `core/error_tracking.py`, `core/log_streams.py` | Sentry only when a DSN is set; structured JSON logs with no secrets |
| Module switches | `middleware/parts.py`, `services/parts.py`, `models/part_settings.py` | Becomes the module registry and `require_module`. The list of modules comes from the installed manifests, not a fixed tuple |
| Settings with history | `services/settings_versions.py`, `services/one_row.py`, `models/version.py` | Typed per-module settings with version history and save-conflict checks |
| App factory | `main.py`, `spa.py` | Builds the app from the kernel and the enabled modules |

**Gate:** tests for each piece, including secret refusal, CSP headers and a module switched off answering 404; the migration round trip; brand check clean.

## K2: auth, to SPEC.md section 14

**Goal:** the complete auth system, test-first. This is the most important phase. Go slowly.

1. **Contract tests first.** Write every test in SPEC.md 14.13 in `kernel/tests/contract/`, as HTTP calls (httpx against the harness) that don't import kernel internals. Commit them failing.
2. **Accounts and access:** one `auth_user` table; roles, role permissions and per-resource overrides (spec 14.1 and 14.8). Sources: Basefra.me team RBAC; `C:\DEV\VybeMindz\per-resource-permission-overrides.zip`.
3. **Passwords:** Argon2id from VybeSite `services/passwords.py`; at least 12 characters for every account (decision 0003); NFC; input capped at 256; the common-password list and the Pwned Passwords range API, failing open with a log line.
4. **Sessions:** opaque 32-byte tokens in `__Host-dk_session`, stored as SHA-256, with the lifetimes in 14.5, rotation at sign-in, step-up and role change, the session epoch, the device list (VybeSite `SignedInDevices`) and the CSRF origin check. VybeSite uses JWTs here; port its behavior (max session age, revocation, device list), not its tokens.
5. **Email codes and magic links:** members only, from VybeSite `services/sign_in_codes.py`; links sign in only through the confirm page's POST.
6. **Reset, verification and email change:** VybeSite `services/password_reset.py`; spec 14.7.
7. **Second factors and step-up:** TOTP with pyotp, recovery codes, `require_recent_auth`; staff blocked from the admin without a second factor.
8. **Passkeys:** the `webauthn` library; discoverable credentials.
9. **OAuth and OpenID Connect:** Authlib; providers from Basefra.me `app/auth/oauth.py` and `app/project_auth/oauth_providers.py`; PKCE, state and nonce; the linking rules in 14.3.
10. **API keys and invites:** Basefra.me `app/auth/api_keys.py` and `app/auth/invites.py`; `C:\DEV\VybeMindz\invite-only-access-control.zip`.
11. **Abuse protection, lifecycle and audit:** spec 14.6, 14.7 and 14.10; security emails; deletion with its 14-day grace period; data export.

**Gate:** every 14.13 contract test passes; each sign-in method works by hand in the harness; brand check, gitleaks and pip-audit clean.

## K3: kernel services

**Goal:** everything else modules rely on.

| Service | Lift from | Notes |
| --- | --- | --- |
| Storage | VybeSite `backup.py` (R2 client); Basefra.me `app/storage/` | Private files only through signed links; provider-fetched files on public, unguessable, expiring links |
| Email | VybeSite `services/email_service.py` | One adapter: SMTP, Mailgun, Resend |
| Notifications | New (Basefra.me's notification center for ideas) | `notify(user, key, context)`, per-person preferences built from manifests, one-click unsubscribe |
| Events | New | The outbox table, the dispatcher, retries and a dead-letter list (spec section 11) |
| Jobs | VybeSite `worker.py` | Postgres-backed queue (`FOR UPDATE SKIP LOCKED`), the scheduler, its lock, budget and retries |
| Moderation | `C:\DEV\VybeMindz\moderation-audit-log.zip`; VybeSite `services/blocklist_service.py`, `contact_filter.py` | Reports, the staff queue, filters, actions, all audited |
| Audit | VybeSite `services/staff_activity.py`; Basefra.me `app/audit/` | Append-only |
| Retention | VybeSite `services/retention_service.py` | Enforces each module's declared retention |
| Public rendering | VybeSite `site_routes.py`, `site_html.py`, `routers/sitemap.py` | Head tags, server copy, JSON-LD, real 404s, `sitemap.xml`, `robots.txt`, `llms.txt` (spec section 9) |
| AI client | VybeSite `services/anthropic_service.py`, `services/ai_key_service.py` | Optional, behind its switch |

**Gate:** tests for each service, including an event delivered once to a handler that's safe to run twice, and a job surviving a worker restart.

## K4: web kernel

**Goal:** the front-end half of the kernel.

- The app shell; `useSession()`; the typed client generated with openapi-typescript and wrapped by openapi-fetch and TanStack Query; `defineModule` and the slots in spec section 8; `<RequireAuth>` and `<RequirePermission>`.
- The UI kit, lifted from `C:\DEV\VybeSite\vybesite\frontend\src\components\` and moved to React 19 and tokens: Accordion, UnsavedDialog, SaveConflict, SectionHistory, RequireAuth, RouteFocus, ErrorBoundary, LoadError, Seo, ScrollMemory, SignedInDevices.
- Auth screens: sign-in, sign-up, codes, passkeys, second factors, devices, account, data export and deletion.
- The admin shell, VybeSite's as it stands (decision 0008).
- Themes: `machined-light` tokens from `C:\DEV\machined-light-design-system`, then `depth` from `C:\DEV\depth-design-system`. Copy tokens only.

**Gate:** component tests, axe with no serious violations, and Playwright runs of every sign-in method.

## K5: CLI and site template

**Goal:** `devkit` works end to end.

- The commands in `cli/README.md`, run as `python -m devkit`, writing lock files that validate against `schema/lock.schema.json`.
- `templates/site/` made from the harness.
- The template's start command runs uvicorn with `--proxy-headers --forwarded-allow-ips` set to the host's edge, and its `.env.example` sets `CLIENT_IP_HEADER` (`X-Real-IP` on Railway). Without them every visitor shares the edge's address, and its rate limits.
- `devkit catalog` regenerating `catalog.json`.

**Gate:** in a temporary folder, `devkit new test-site` with the kernel only (no recipe modules exist yet) builds, migrates and passes its tests; `devkit check` passes on it.

## The kernel is done when

- Every row of SPEC.md section 16 passes for the kernel, in CI.
- The auth contract tests pass.
- The brand check, gitleaks, pip-audit and npm audit are clean.
- `CLAUDE.md` (commands, current state), `docs/HANDOFF.md` and the decision records are current, and the owner has the list of spec sections to sync into the design doc.

Then write the next kickoff, `dev plans\<date>-next-session-modules-wave-1.md`: `pages`, `blog`, `embeds`, `contact` and `campaigns` from VybeSite with the `devkit-module-extractor` skill, on the Vibrant Mindz build order (`docs/plans/vibrant-mindz-module-plan.md`, section 11).

## Every session ends with

1. `docs/HANDOFF.md` overwritten.
2. "Last Completed Task" and "Current state" updated in `CLAUDE.md` and `AGENTS.md`.
3. A starting prompt for the next session, about 4 KB, saved as `dev plans\<date>-next-session-<topic>.md` and offered to the owner.
