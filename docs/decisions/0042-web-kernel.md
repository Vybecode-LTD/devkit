# 0042: The web kernel: a typed client from committed specs, kernel pages in one list, `--mf-*` tokens, and the admin to the boards

- **Date:** 2026-11-18
- **Status:** Decided; applied in K4, PR by PR (#78 is the typed client)
- **Context:** K4 builds the kernel's front end (KICKOFF K4, SPEC 6, 8, 9 and 16). It touches seams other code depends on:
  - the typed client modules call the API with;
  - `defineModule`'s slots;
  - the addresses the server and the React router must agree on;
  - the theme tokens every module styles with;
  - the admin's routes.

  So its contract came first: `dev plans/contracts/k4-web-kernel.md`. Reading the code for it found four things:
  - No route declared what it answers (every one returned `dict[str, Any]` or a raw response), so a client generated from the OpenAPI document would have known nothing of the answers.
  - The device list's three routes (K2 step 4's contract) were never built; their contract tests are strict-xfail.
  - There are no HTTP routes yet for settings, module switches or people and roles.
  - The kernel's mails already link to eight web pages the server answers 404.
- **Decision** (the owner approved the contract on 2026-11-18, with the four answers below):
  1. **Every route declares a typed answer.** An `Answer` model (`kernel.answers`) refuses keys it doesn't name. A route that returns a dict names it as `response_model`, which FastAPI checks on the way out. A route that sets a cookie or header builds its JSON with `answer(Model, content)`, which checks it the same way. So an answer can't drift from the spec without a 500 in the tests. The JSON is unchanged: ids and times were already strings. A sign-in's answer is a union told apart by `status`.
  2. **The specs are committed and the client is generated from them.** `python -m tools.openapi` writes `kernel/openapi.json` (the paths under `/api/auth` and `/api/kernel`) and each module's `openapi.json`, with `--check`. It documents errors as they are: every operation's 422 and `default` are `application/problem+json` (`Problem`), and FastAPI's own validation shapes are gone. `npm run api:types` makes `kernel/web/src/api/schema.ts` with openapi-typescript, and `npm run api:check` (in CI) fails when it's stale.
  3. **The client.** openapi-fetch, with TanStack Query hooks from openapi-react-query: `api`, `useApiQuery`, `useApiMutation` and `apiQueryOptions` for the kernel's paths, and `createApiClient<paths>()` for a module's. Any answer but a success throws an `ApiProblem`; a failed network is status 0, `kernel.unreachable`. A 401 `kernel.not_signed_in` tells the session. A write refused with 403 `auth.step_up_required` asks the person to confirm it's them and then resends its copy of the request, once; a read never asks.
  4. **The kernel's own pages are one list** in `kernel/kernel.json`, read by the router and by the server's shell, which answers each 200 with noindex. It covers sign-in, sign-up, forgot password, the eight email landings, the account pages and the admin's. A landing takes its token out of the address bar and acts only on a button press.
  5. **Tokens are `--mf-<path>`.** The old `--dk-` prefix was missed by decision 0034's rename. Every theme defines the kernel's required tokens (colour roles, type, shape, motion).
     - The colour roles come from the Vibrant Mindz theme's names, with Machined Light mapped into them. Machined Light has no hover, focus, link or status roles, and its `text-strong` is the lower-contrast text, so the README's plan to rename to its names couldn't hold.
     - The primary button hovers to `accent-hover`.
  6. **The server's words** in `[data-server-copy]` are hidden by `@media (scripting: enabled)` in a browser running JavaScript. They show after 3 s if the app never loads, and at once to a reader without JavaScript. This is pure CSS: no script, no CSP change.
  7. **The admin** is built to the boards (decision 0040). It covers Dashboard (with a "Needs you" list from `GET /api/kernel/admin/attention`), People, Roles with New role and editing, Activity, and Settings (Site, Features, System).
     - **Roles:** only custom roles can be edited. The built-in roles stay as the manifests declare them, so the admin role can't be stripped and lock everyone out. Editing needs the new `auth.role.manage` and a step-up.
     - **System:** retrying and discarding failed jobs needs the new `kernel.jobs.manage`.
     - **Site:** fields the Site board draws that no settings section holds (tagline, address, contact email, time zone) are left off, not faked.
  8. **End-to-end tests** (Playwright, Chromium) run locally before every push, and in CI on main's pushes, weekly and by hand, never on a PR.
  9. **Depth waits** until a site wants it. K4 ships Machined Light (the default) and Vibrant Mindz.
- **Alternatives:**
  - *Answers:* hand-written TypeScript types for the answers (they drift from the server); response models without the outbound check (they drift too, silently).
  - *Client:* writing the TanStack Query generics by hand instead of openapi-react-query (more code to get wrong; it adds no transitive packages).
  - *Server copy:* the 1.5 s CSS timer (VybeSite's; readers without JavaScript wait), the words first with a cross-fade (every visitor sees the plain version), always shown, never shown.
  - *Admin scope:* the core screens with read-only roles and no System (recommended, not chosen); the shell alone.
  - *End-to-end tests:* on every web or kernel PR (recommended; more Actions minutes).
- **Consequences:**
  - openapi-typescript asks for TypeScript ^5 as a peer while the repo is on 6.0.x, so `package.json` overrides it. The generator runs fine on 6, and `api:check` passes.
  - Generated files keep LF (`.gitattributes`).
  - SPEC 4, 6, 7 and 18 change with #78. SPEC 8, 9, 14.8 and 16 change with the PRs that build them.
  - Contract changes after approval are listed in the contract and flagged in the handoff.
- **See:** `dev plans/contracts/k4-web-kernel.md`; decisions 0004, 0040, 0041
