---
feature: K4 web kernel (the app shell, the typed client, session, guards, slots, themes, the UI kit, the auth and account screens, the admin shell)
status: approved
approved: 2026-11-18 (the owner: "Approve", with the four answers in §8)
plan: KICKOFF.md K4; SPEC 6, 8, 9 and 16; decision 0040; docs/HANDOFF.md, Next
pr: 78 first (predicted; #77 is the last); the order in §4
---

# Contract: K4 web kernel

## 1. Goal

A MechFrame site has a working front end: a visitor reads public pages (the server's words first, then React), signs up and signs in by every method K2 built, and manages their account; staff run the site from an admin built to the Vibrant Mindz canvas boards, styled by tokens, in either theme. A module's binding plugs its pages and slot entries into the shell with one `defineModule` call and talks to its API through a client typed from the committed `openapi.json`.

## 2. Interfaces

**Web public surface** (`kernel/web/index.ts`; test helpers in `kernel/web/testing.ts`, never in a visitor's bundle):

```ts
mountApp(options: AppOptions): Promise<Root>   // createRoot(options.root ?? #root), never hydrateRoot; drawn once the modules on are read (changes 12, 13)
type AppOptions = { modules: ModuleDefinition[]; adminSections?: AdminSection[]; root?: HTMLElement };
type AdminSection = { label: string; icon: IconName };   // the sidebar's order and icons for module sections

api; useApiQuery("get", path, init?, options?); useApiMutation(method, path, options?); apiQueryOptions("get", path, init?, options?)   // the kernel's paths
createApiClient<Paths>(options?: { fetch?; baseUrl? }): { api; useApiQuery; useApiMutation; apiQueryOptions }   // a module's api.ts; the options are for tests
class ApiProblem extends Error { status; code; title; detail; errors: Record<string, string[]>; extra }

useSession(): Session; useSignOut(): () => Promise<void>
type SessionUser = { id; email; roles: string[]; permissions: string[]; verified: boolean; second_factor: boolean };
type Session = { status: "loading" } | { status: "signed-out" } | { status: "unreachable"; problem: ApiProblem; retry(): void }
  | { status: "signed-in"; user: SessionUser; staff: boolean; can(permission: string): boolean };
<RequireAuth> <RequirePermission permission="…">     // useModuleEnabled(id); useSite(); useSettings(id) (admin form)
useSlot(name); <SlotOutlet name="…">                 // <Seo title description? path? image? type? noindex?>
renderWithKernel(ui, { path?, session?, modules? })  // testing.ts, for every module's component tests
```

- **The client** is openapi-fetch over types from openapi-typescript. Same origin, cookies only. Any non-2xx answer throws `ApiProblem` (a network failure is status 0, `kernel.unreachable`). A 401 `kernel.not_signed_in` sets the session to signed out. A mutation that gets 403 `auth.step_up_required` opens the step-up dialog and retries once; a query never does. Query keys are openapi-react-query's, `[method, path, init?]` (change 1 below; cubic on #78).
- **`useSession`** reads `GET /api/auth/session`; `staff` is any role but `member`. A sign-in's answer sets it directly.
- **Guards:** signed out → `/sign-in?next=<path>`, and `next` is only ever a same-site path (one leading `/`, no `//` or `\`). Without the permission: the kernel's no-access page, never a redirect. The admin itself: a member gets the 404 page; staff without a second factor go to `/account?needs=second-factor`.
- **`defineModule`'s slots become typed** (today `Record<string, SlotEntry[]>`):

```ts
type LinkEntry = { label: string; to: string; permission?: string };
type Slots = {
  "nav.public"?: LinkEntry[]; "nav.member"?: LinkEntry[];
  "nav.admin"?: (LinkEntry & { section?: string; icon?: IconName })[];
  "admin.dashboard.widget"?: { lazy: Lazy; permission?: string }[];
  "admin.settings.section"?: { id: string; title: string; lazy: Lazy; permission?: string }[];
  "account.section"?: { id: string; title: string; lazy: Lazy }[];
  "site.footer"?: { lazy: Lazy }[];
};
```

  `useSlot` gives only modules that are on and entries the user may see. The sidebar: Dashboard, then module entries grouped by `section` in `adminSections` order (unlisted sections after, as they appear), then People and access, then Settings. Each lazy entry renders in its own error boundary.
- **Routes:** every module route is lazy. A module that's off renders the 404 page. Public and kernel pages sit in the site frame (`nav.public`, `site.footer`), member pages behind `<RequireAuth>`, admin pages in the admin shell. Routing is a data router (`createBrowserRouter`), which the unsaved-changes guard needs.
- **Server copy:** the words in `[data-server-copy]` are styled by the theme. In a browser running JavaScript, `@media (scripting: enabled)` hides them until React replaces them. A safety net shows them after 3 s anyway, in case an extension blocks the app or it fails to load. Readers without JavaScript see them at once. This is pure CSS: no script, no timer for those readers, no CSP change.
- **`<Seo>`** updates the server's head tags in place, never duplicating them, and drops the first page's JSON-LD after a client navigation.

**The kernel's own pages**, one list in `kernel/kernel.json` (`pages: [{path, title, access}]`), read by the React router and by `shell.py`. Each answers 200 with the shell, `noindex`, "{title} · {name}". The start refuses a module pattern that matches one. The email landings already exist in the kernel's mails.

| Access | Pages |
| --- | --- |
| public | `/sign-in` (password, passkey, email code or link; the second step), `/sign-up`, `/forgot-password`; landings `/auth/verify`, `/auth/link`, `/auth/reset`, `/auth/email`, `/auth/email/undo`, `/auth/second-factor/undo`, `/notifications/unsubscribe` |
| member | `/account` (passkeys, authenticator app and recovery codes, password, email, signed-in devices, then `account.section`), `/account/notifications`, `/account/activity` |
| admin | `/admin` (Dashboard), `/admin/people`, `/admin/roles`, `/admin/activity`, `/admin/settings` (Site, then `admin.settings.section`), `/admin/settings/features`, `/admin/settings/system` |

A landing takes `?token=` out of the address bar before it renders. It acts only when the person presses its button, never on load, because mail scanners open links.

**Backend additions** (each with contract tests over HTTP):

1. **Response models** on every `/api/auth` and `/api/kernel` route, so the client is typed end to end; the JSON doesn't change. `python -m tools.openapi` writes `kernel/openapi.json` (and each module's, SPEC 4), with `--check`.
2. `GET /api/kernel/site` (public): `{name, description, kind, logo, card_image, same_as}`.
3. auth-api.md's `GET /api/auth/sessions` (items `{id, device_label, location, started_at, last_seen_at, current}`), `DELETE /api/auth/sessions/{id}` and `POST /api/auth/sessions/sign-out-others`. No test calls them yet: their contract tests are written first, seen failing.
4. auth-api.md's `GET /api/auth/admin/users?q=&cursor=&limit=` (items `{id, email, roles, verified, second_factor, status, created_at, last_seen_at}`) and `PUT /api/auth/admin/users/{id}/roles`. New: `GET /api/auth/admin/roles`, giving `{roles: [{id, name, description, permissions, people, builtin}], permissions: [{key, description, owner}]}` (`auth.user.manage`).
5. **Editing roles** (new; SPEC 14.8 and auth-api.md). All need the new permission `auth.role.manage` ("Create, edit and delete roles, within the permissions you hold"; admin by default) and step-up:
   - `POST /api/auth/admin/roles` (`{id, name, description, permissions}`, the id `^[a-z][a-z0-9-]{1,63}$`) → 201.
   - `PUT /api/auth/admin/roles/{id}` (`{name, description, permissions}`) → 200.
   - `DELETE /api/auth/admin/roles/{id}` → 204.
   - **Refusals:** 403 `auth.role_not_yours` for a permission you don't hold; 422 `auth.permission_unknown`; 409 `auth.role_exists`; 409 `auth.role_builtin` (the built-in roles stay as the manifests declare them, so only custom roles change); 409 `auth.role_in_use` when deleting a role someone holds.
   - A change raises its holders' role version, so their next request gets a new session token, as assigning does. It's audited as `auth.role.created`, `auth.role.changed` or `auth.role.deleted`.
6. `GET` and `PUT /api/kernel/admin/settings/{id}` (`{version, values}`; `PUT {version, changes}` → `{version, changed, merged}`, or 409 `kernel.settings_conflict` as built) and `GET /api/kernel/admin/settings/{id}/history`, all `kernel.settings.manage`. The Site tab shows the fields a settings section holds (`kernel.site` and the auth section). The board's tagline, address, contact email and time zone have no home yet, so they're left off, not faked. The name is `SITE_NAME`, shown read-only.
7. `GET /api/kernel/admin/modules` (`{items: [{id, name, summary, on, requires, required_by}]}`) and `PUT /api/kernel/admin/modules/{id}` (`{on}`), both `kernel.module.manage`.
8. **System** (new; `kernel.settings.manage` to read; the new permission `kernel.jobs.manage`, "Retry and discard failed background jobs", admin by default, to act):
   - `GET /api/kernel/admin/system` → `{jobs: {queued, running, dead, worker: "ok" | "behind"}, services: {email, storage}, version, modules}`. `behind` means a queued job is more than 2 minutes past due. `email` is the adapter (`smtp`, `resend` or `log`), and `storage` says whether it's configured.
   - `GET /api/kernel/admin/jobs/dead?cursor=&limit=` → `{items: [{id, name, module, tries, last_error, failed_at}], next_cursor}`. A job's payload is never shown.
   - `POST /api/kernel/admin/jobs/{id}/retry` → 200 `{state: "queued"}`, and `DELETE /api/kernel/admin/jobs/{id}` → 204. Both answer 409 `kernel.job_not_dead` for a job that isn't dead, and are audited as `kernel.job.retried` and `kernel.job.discarded`.
9. `GET /api/kernel/admin/attention` (staff): the "Needs you" list, `{items: [{key, tone, what, why, action: {label, to}}]}`, each item only for people who can act on it. The kernel's items are `kernel.site.description_missing`, `kernel.site.card_missing` and `kernel.jobs.dead`. Modules add theirs through the dashboard cards hook.

**Themes:** a theme's tokens are `--mf-<path>`; `--dk-` came from the old name, and decision 0034 missed it. Every theme defines the kernel's required tokens, listed with their meaning in `themes/README.md` and read by its test:

- **Colour:** `canvas`, `rail`, `surface`, `surface-raised`, `well`, `text`, `text-strong` (the highest contrast), `text-muted`, `text-subtle`, `border`, `border-strong`, `accent`, `accent-hover`, `on-accent`, `focus`, `link`, `link-hover`, `success`, `warning`, `danger`.
- **Type:** `font.display`, `font.text`, `font.mono`; `type.page-title`, `type.section-title`, `type.body`, `type.small`, `type.meta`.
- **Shape and motion:** `radius.control`, `radius.card`, `radius.pill`; `layout.sidebar`; `motion.fast`, `motion.base`.

The primary button hovers to `accent-hover`. `python -m tools.themes` writes each theme's `tokens.css` and `tailwind.css`, with `--check`.

## 3. Data

None: no tables or migrations. Settings, switches, roles and sessions already have their rows.

## 4. Files, in PR order

1. **#78, the typed client:** response models in the kernel's routers; `tools/openapi.py`; `kernel/openapi.json`; `kernel/web/src/api/` (`schema.ts`, generated, and `client.ts`). Also this contract, decision 0042, and SPEC 4, 6, 7 and 18; SPEC 8, 9, 14.8 and 16 change with the PRs that build them.
2. **The app shell:** `kernel/web/src/{app,session,guards,slots,site,seo}/`; `kernel.json` pages; `shell.py`; `GET /api/kernel/site`; harness `index.html` with the markers; `playwright.config.ts`; `kernel/tests/e2e/parity.spec.ts`; a CI E2E job that runs on main's pushes, weekly and by hand, never on a PR. Before every push, I run the suite locally and put the result in the PR.
3. **Themes:** `themes/README.md`; `themes/machined-light/` (values from `C:\DEV\machined-light-design-system`, mapped to the kernel's names); `themes/vibrant-mindz/` (copied, renamed, census rerun in VM Website); `tools/themes.py`; the token lint.
4. **The UI kit**, ported from VybeSite and drawn from `admin_kit.py`'s parts (`kernel/web/src/ui/`): Button, Field, Card, Pill, Attention, Accordion, Tabs, Table, Dialog, UnsavedDialog and the guard hooks, SaveBar, SaveConflict, SectionHistory, Toast, EmptyState, LoadError, ErrorBoundary, RouteFocus, ScrollMemory, Icon.
5. **Auth and account screens** to `Auth.dc.html` and `Account.dc.html`, with the step-up dialog, the session routes, and `kernel/tests/e2e/sign-in.spec.ts`.
6. **Admin shell:** the sidebar, the top bar (Ctrl K jumps to any admin page you can see; notices; View site), the page header, Dashboard and Activity, and the attention route.
7. **Admin people and roles:** People, and Roles with New role and editing (additions 4 and 5, `auth.role.manage` in `kernel.json`). The auth threat checklist applies.
8. **Admin settings and system:** Site, Features and System (additions 6 to 8, `kernel.jobs.manage` in `kernel.json`).

## 5. Conventions this follows

- **Skills:** `server-copy-for-crawlers`, `verify-real-pass` (rendered contrast), `web-mockup-parity`; the owner's rule that an approved board is the specification.
- **Design brief:** VM Website `design/specs/admin-look.md`; the boards in `design/site/`.
- **Ported from VybeSite** (behavior, not looks):
  - `lib/api.ts`, `context/AuthContext.tsx`, `main.tsx`;
  - `lib/unsavedGuard.ts`, `lib/settingsSave.ts`, `lib/returnTo.ts`, `lib/pageFocus.ts`, `lib/chunkReload.ts`;
  - its cascade layers.
- **Patterns:** `tools/event_schemas.py` for the generators' `--check`.

## 6. Non-goals

- No server rendering or hydration, no visitor theme switch, no change to the CSP (no inline style or script).
- Tailwind's packages don't join yet: the kit is plain CSS on tokens in cascade layers, and each theme's `tailwind.css` waits for the first page that uses a utility.
- Not built in K4:
  - outside sign-in buttons, invites, API keys, and account deletion and export (K2 steps 9 to 11);
  - the moderation queue screen (site step 4);
  - modules' "Needs you" items (the dashboard cards hook) and content search in Ctrl K (the search index hook);
  - a public `useSettings` for modules.
- Changing the built-in roles' permissions (only custom roles are edited), per-resource overrides in the admin, and service health checks beyond the adapter and configuration.
- Depth (the owner, 2026-11-18: later, when a site wants it).
- No i18n, no realtime, no service worker.

## 7. Acceptance

- **Backend:**
  - `tests/test_openapi.py`: committed specs are current, and every kernel route has a response model.
  - Contract tests for additions 2 to 9, the session routes' among them. Role editing gets a test for each refusal, and one that a holder's next request carries a new session token.
  - `test_shell.py`: kernel pages answer 200 with noindex, and a module pattern that overlaps one is refused.
  - Coverage stays at 95 % or more.
- **Vitest:** the client (problems, 401, step-up retried once), session, guards (`next` cleaned), slots (off modules and permissions hidden, sidebar order), `defineModule`'s checks, kernel pages equal to `kernel.json`'s, `<Seo>` without duplicates, and every kit part and screen. Web coverage reaches 85 % per PR.
- **Playwright** (Chromium, the harness with its test support; run locally before each push, and in CI on main's pushes and weekly):
  - every sign-in method: password; password plus TOTP, a recovery code or a passkey; passkey alone (virtual authenticator); email code; magic link;
  - sign-up and verify, reset, the account's factors and devices;
  - a smoke test of each admin page;
  - parity on `/`: every visible `h1` to `h3` and `p` is in the server copy;
  - axe on every page in both themes, with no serious or critical violations.
- **Themes:** `tests/test_themes.py` (required tokens present, references resolve, contrast pairs, reduced motion, files current); no colour literal outside `themes/`.
- **By eye:** each built auth, account and admin screen beside its board at 1440 and 390 px in the Vibrant Mindz theme, with screenshots in `dev plans/` and contrast measured as rendered in both themes. Only then is it done.

## 8. Open questions

None. The owner answered all four on 2026-11-18:

1. **Admin scope: core plus roles and System**, over core only (recommended: Roles read-only, no System) and shell only. Added: role editing, New role, Settings › System. Invites (K2 step 10) and the moderation queue (site step 4) are still later.
2. **The server's words: the CSS `scripting` query**, over the 1.5 s timer (first recommended), words first with a cross-fade, words always shown and never shown. The owner asked for something more elegant than the first three.
3. **End-to-end tests in CI: weekly and on main only**, over every web or kernel PR (recommended). I run them locally before every push.
4. **Depth: later**, as recommended.

## Changes after approval

Made while building #78 (decision 0042 records them):

1. **The hooks come from openapi-react-query**, which the contract didn't name. It adds no transitive packages: it uses openapi-fetch's helpers. Its query keys are `[method, path, init?]`, not `["api", method, path, init]`. `apiQueryOptions` is exported too, for `fetchQuery` and `prefetchQuery`. The hooks' types are restated over `openapi-typescript-helpers` (now a declared dependency, the version openapi-fetch already pulls): their error is an `ApiProblem`, and a query takes reads only.
2. **`createApiClient(options?)`** takes `{fetch, baseUrl}`, for tests only.
3. **The backend's public surface gains `Answer`, `answer`, `Id` and `When`** (SPEC 6 and 7), since a module's routes declare their answers the same way.
4. **openapi-typescript is held to TypeScript 6 by an override.** It asks for `^5` as a peer and runs fine on 6. Generated files keep LF (`.gitattributes`), so `--check` compares the same bytes on Windows and Linux.
5. **What two required tokens mean, for the themes PR.** This came from the VM Website session, with the owner's OK, at 2026-11-18 14:05 Eastern; details in VM Website `design/theme/vibrant-mindz/shell-slots.md`.
   - `border` is the edges of cards, dividers, table rows, the sidebar and the top bar. `border-strong` is the edges of controls: buttons, inputs, badges, chips and the save bar.
   - So Machined Light's `--color-border`, its control border, maps to `border-strong`. Its cards take their edge from a shadow.
   - `font.mono` is the code face. Vibrant Mindz's is `typography.fontFamily.code` (ui-monospace). Its `mono` is Doto, a homepage display face.
6. **The withdrawn picomatch advisory.** GitHub withdrew GHSA-fc5q-39xc-vjpf on 2026-11-18 at 15:38 UTC, and npm audit stopped reporting it. `tools/npm_audit` fails on an allowance npm no longer reports, by design, so #78 empties `tools/npm_audit_allow.json`. The 2026-12-17 recheck is gone with it.
7. **The device list has no contract tests yet.** §2 and §7 first said its routes had strict-xfail tests to turn green. None calls them (CodeRabbit on #78), so the account PR writes them first.
8. **The kernel's pages: one list in `kernel.json`, kept in code by each side.** §2 said both the React router and `shell.py` read the list from `kernel/kernel.json`. But neither can read it when running: a site copies the kernel's backend and web folders, never the manifest. So `kernel.json` keeps the list, `shell.py` and the router each hold it in code, and tests hold both equal to the manifest, as `KERNEL_PERMISSIONS` already is (cubic on #78). Built in #79: the backend's copy is `kernel.server_copy.KERNEL_PAGES`, beside `KERNEL_FILES`, which `shell.py` reads; the router's is `kernel/web/src/app/pages.ts`, which also names each admin page's permission.
9. **Which module routes "match" a kernel page (#79).** §2 said the start refuses a module pattern that matches one. Read literally, that refuses `/:slug`, which a pages module needs. So a route is refused when it takes a kernel page under the kernel's own first segment (`/sign-in`, `/account/:tab`, `/auth/:step`, `/admin/people`); one that starts with a `:name` may meet them and never gets them, since the server answers a kernel page before asking any module and the router ranks fixed paths first. The server's `Routes.resolve` gives a kernel page to no module, so the sitemap and `llms.txt` never list one. `defineModule` refuses the same routes in the browser.
10. **What #79 leaves for later PRs.** `IconName` is any string until the UI kit (K4.4) brings its icon set. `useSettings` lands with the admin settings routes (K4.8). The kernel's pages show their heading and "This page isn't ready yet." until their screens are built. `testing.ts` also gives `renderApp` (the whole router), `testUser` and `TEST_SITE`. The frames have a small base stylesheet (`frames.css`: menus that wrap, targets of 24px at least, which axe's WCAG 2.2 check asked for); K4.3's themes build on it.
11. **Where the end-to-end tests run (#79).** Playwright's server is `python -m harness.e2e`: the harness with its test support and `WEB_DIST`, on a `mechframe_e2e` database it drops and makes again at each start, with a description given to the site so the home page's parity compares a paragraph. The CI job is a workflow of its own, `.github/workflows/e2e.yml`, outside "CI result". It uploads no traces yet: that needs an upload action pinned like the others.
12. **`mountApp` returns a promise, and the router holds only the modules on (Codex on #79).** §2 had `mountApp(options): void` and a module that's off answered by its own route with the 404 page. But then an off module's more fixed route kept an address from an on module's broader one (`/blog/:slug` off, `/:section/:slug` on), which the server gives to the module on. So `mountApp` reads `GET /api/kernel/modules` once, then builds the router from the modules on (every module if it can't be read), and returns `Promise<void>`; the page and the modules are still checked at once, and a mistake still throws there. A module switched off while the app is open becomes the 404 page once the app reads the switches again: on the next page opened, or the window's next focus, once they're five minutes old. `RouteFocus` also waits for a lazy page's heading to appear; after 3 s it focuses the main area meanwhile, and still moves on to the heading when it comes (watched for 30 s at most). The moment the person moves the focus themselves, or goes to another page, all of it stops.
13. **From cubic's and CodeRabbit's reviews of #79.**
    - `mountApp` resolves to its React root, so a host page or a test can unmount it.
    - `setSessionUser` returns a promise: it first stops any session read on its way. A 401 on any call other than the session's own now reads the session again, and forgets what was the person's only if it's gone, since the call may have been sent before a sign-in.
    - The router matches with case, as the server does. A module's switch is checked before its sign-in or permission.
    - A failed read of the modules on or of the site shows the "can't be reached" page with Try again, not a blank one (`useSiteRead`, `useModulesRead`).
    - `<Seo>` takes `published` and `modified`.
    - Slot entries keep keys made before filtering. A part whose code didn't arrive loads again on Try again.
    - `defineModule` refuses the ids `auth` and `kernel`, reads admin links as the browser resolves them, and counts optional segments and trailing slashes when checking kernel pages.
    - `safeNext` checks only the path part for `//` and backslashes.
    - `testing.ts` takes `on: "loading"`, `site: "loading"` and `strict`.
    - Node is 22.12 at least. CI's Web job enforces the 85 % floor.
    - The end-to-end server reads no `.env` and never reuses a running server.
14. **The themes (#80).**
    - A theme's tokens sit on `[data-theme="<name>"]` alone, never `:root`: a site names its theme on `<html data-theme>` in its `index.html`. The harness imports both themes and names Machined Light, and Playwright switches the attribute to run axe in each.
    - A `type.*` token is a W3C typography composite. It writes a `font` shorthand (`--mf-type-body`) and its tracking (`--mf-type-body-tracking`).
    - The required list is §2's, unchanged. The admin's focus-ring shadows stay in the Vibrant Mindz theme and join the list when the kit needs them.
    - **Machined Light's roles:** where the system's own role fails AA as text, the kernel's takes the next shade that passes (accent ember-600, text-muted neutral-700, text-subtle neutral-600; focus stays its own ember-500, 3.4:1), and the three signals gain a text shade derived on their own hue. `themes/machined-light/README.md` lists each. These are my calls, for the owner to confirm.
    - **Vibrant Mindz** is VM Website's `tokens.json` with the kernel's `font`, `type`, `radius` and `motion` names added as aliases, so no value changed. Pointing its census at the copy is VM Website's work.
    - The colour rule is ESLint's `no-restricted-syntax` for TypeScript and `tests/test_themes.py` for CSS; SPEC 16 named Stylelint, which isn't added. The frames' base styles now use the tokens.
    - `color.border-strong` isn't held to 3:1 in either theme: a control also takes its edge from a fill or a shadow. **K4.4:** check each kit control's boundary as a whole reaches 3:1 (WCAG 1.4.11), since axe doesn't (cubic on #80).
