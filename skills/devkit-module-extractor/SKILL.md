---
name: "devkit-module-extractor"
description: "Turn a feature from an existing project into an AI DevKit module: pick the best source, cut its dependencies, reshape it to the module contract (manifest, kernel API, migrations, tests) and record where it came from."
---

# DevKit module extractor

Use this when lifting a feature (auth, blog, chat, payments, a forum, an embed system) out of an existing project and into the AI DevKit as a reusable module, or when porting a module from another stack (Supabase, Node/Express, Next.js) onto DevKit's stack. The result is a folder that passes the DevKit quality gate and that any agent can copy into a site.

The DevKit spec (`SPEC.md` in the DevKit repo; the design doc "AI DevKit Spec") is the contract. Re-read sections 4 to 13 and 16 before starting, because the spec changes. Where this skill and the spec disagree, the spec wins. If the `devkit` CLI isn't built yet, do its steps by hand as spec section 12 describes.

**The stack:** Python 3.12+, FastAPI, Pydantic v2 (strict), async SQLAlchemy 2 with asyncpg, Postgres, Alembic with one branch per module; React 19, Vite, TypeScript strict, React Router 7, TanStack Query, design tokens as CSS variables.

## The rule that matters most

Extracting is not copying. Pick the one best source for the feature, then reshape it to the contract. Never merge three half-versions of a feature into one module, and never carry the source project's auth, branding or data along.

## Step 1: choose the source

1. Search for every implementation of the feature across the owner's projects (for example under `C:\DEV`). Check the DevKit inventory doc first; it already lists best sources per category.
2. Rank them by: tests that exist and pass, how hardened the code is (security reviews, audit logs, bug notes), closeness to the DevKit stack, and how little it depends on the rest of its project.
3. Read the chosen project's `CLAUDE.md`, `docs/`, bug notes and decision records before touching code. They record what went wrong last time.
4. Note the runner-up sources. They are for ideas only; their code doesn't go in.

## Step 2: provenance gate (stop if it fails)

- Confirm the code is the owner's to reuse. Client-confidential code and material never enter DevKit (for this owner: nothing from the client folder named in `docs/private/README.md`).
- For code lifted from VybeSite, run VybeSite's private brand check on the extracted files before they land. Never copy the check's term list into DevKit.
- Strip real customer data, fixtures with real people's details, keys, `.env` files, analytics ids, domain names and brand copy.
- Record `source` in `module.json`: project, commit, path, license.
- If ownership is unclear, stop and ask the owner.

## Step 3: inventory the feature

Build this table before writing anything:

| Part | What to list |
| --- | --- |
| Routes | Every endpoint, its method, who may call it |
| Data | Tables, columns, indexes, constraints, triggers, row-level-security policies |
| Logic | Services, background jobs, scheduled tasks |
| Side effects | Emails, webhooks in and out, events, files written, third-party calls |
| Config | Settings, env vars, secrets |
| UI | Pages, components, stores, styles |
| Tests | What exists, what passes |

Useful commands: `rg -n "@router\.|APIRouter|app\.(get|post|put|patch|delete)" <src>`, `rg -n "__tablename__|create table" -i <src>`, `rg -n "^from |^import " <src>/<feature>` for imports.

## Step 4: cut the dependencies

Sort every import and call into one of four piles:

1. **The kernel already does this.** Replace it with the kernel's public API (spec section 6).
2. **Another feature does this.** Replace the call with a kernel event, or list that module under `requires.modules` and call only its `public.py` (backend) or `web/public.ts` (front end).
3. **Specific to the old project.** Drop it, or turn it into a setting.
4. **A third-party library.** Keep only if needed, and justify it in the PR.

| Source pattern | DevKit replacement |
| --- | --- |
| Its own login, JWTs, session tables | `current_user`, `optional_user`, kernel sessions (spec 14) |
| Role checks, admin flags | `require_permission("<id>.<resource>.<action>")`, declared in `permissions` |
| **Supabase row-level security** | Server-side permission and ownership checks in every route and service. RLS protections silently vanish in a port unless each policy is rewritten and tested |
| Supabase client queries | SQLAlchemy models and services |
| Supabase triggers (such as a new-user trigger) | Handlers on kernel events such as `auth.user.created` |
| Supabase Storage | `storage.put / get / signed_url` |
| Express or Next.js middleware | FastAPI dependencies |
| Its own email sending | `email.send` or `notify` |
| Its own rate limiter | `rate_limit` |
| Its own report or ban tools | `moderation.report / queue / act` |
| Stored secrets in plain text | `crypto.seal / open` |
| Zustand or Redux stores of server data | TanStack Query through the generated client |
| `fetch` calls in components | The generated client (`api`, `useApiQuery`) |
| Tailwind color classes, hex values | Theme tokens (`var(--dk-*)`) |
| Hard-coded numbers and copy | Settings |

Make a list of every RLS policy, trigger and middleware in the source, and tick each off as re-implemented with a test. This is where ports go wrong.

## Step 5: scaffold the folder

```
modules/<id>/
  module.json
  MODULE.md
  CHANGELOG.md
  backend/<id_>/  models.py schemas.py service.py router.py   (<id_> = id with _ for -)
                  events.py jobs.py server_copy.py public.py   (only those needed)
  migrations/     Alembic branch "<id>"
  openapi.json    generated, committed
  web/            module.web.ts routes.tsx pages/ components/ api.ts public.ts
  tests/          backend/ web/ e2e/ contract/
```

## Step 6: write module.json

Fill every field the spec's schema requires. The two that decide whether agents ever pick the module:

- `use_when`: 2 to 4 concrete sentences about the site, matchable against a brief. Good: "The site sells usage rights to music files". Bad: "Monetization".
- `avoid_when`: 1 to 3 sentences that name the better choice. Good: "Visitors only need to react to posts; use comments instead".

Also declare `permissions` (with default roles), `settings`, `env`, `routes`, `tables`, `events`, `slots`, `notifications`, `jobs`, `data_hooks` and `source`. Start `status` at `experimental`.

## Step 7: port the backend

- Package and tables: the Python package is the id with hyphens turned into underscores (`print-on-demand` becomes `backend/print_on_demand/`), and tables are named `<id_>_<name>`, UUID keys, `timestamptz` in UTC, money as integer minor units plus currency. Foreign keys only to the module's own tables and `auth_user`.
- Migrations: one Alembic branch for the module, labelled with its id, whose first revision has `depends_on` set to the kernel revision it needs (such as `kernel_0002`, which made `auth_user`). Name revisions `<id_>_NNNN`. Make one with `command.revision(cfg, autogenerate=True, rev_id="<id_>_0001", head="base", branch_label="<id>", version_path="modules/<id>/migrations", depends_on="kernel_0002")` using `harness.migrations.config(url)`; later ones with `head="<id>@head"`. Every migration downgrades cleanly; mark data-destroying ones `destructive = True`. The `alembic-multi-module-migrations` skill has the details.
- Schemas: Pydantic in strict mode for every body. Cursor pagination for lists.
- Router: thin, `router = APIRouter()` in `router.py`, mounted by the kernel at `/api/<id>` behind `require_module("<id>")`, admin under `/api/<id>/admin`. Every route declares its access with `Depends(public)`, `current_user` or `require_permission(...)` (the kernel's route audit fails any that doesn't), nothing changes state on GET, and errors are `raise Problem("<id>.<snake_case>", status, detail)` (RFC 9457 with a stable `code`).
- Fixed names the kernel looks for (decision 0009): `schemas.py`'s `Settings` (every field defaulted, secrets typed `SecretStr`; read with `await settings.for_module(db, "<id>")`), and `__init__.py`'s `CSP`, the (directive, https origin) pairs the module adds to the Content-Security-Policy while it's on.
- Service: all logic; slow work (over about a second) goes to `jobs`.
- Events: versioned Pydantic payloads holding ids, emitted inside the transaction; handlers safe to run twice.
- Public pages: `server_copy.py` with `head`, `copy`, `structured_data` and `sitemap`, so crawlers that run no JavaScript read the page.
- Personal data: `export_user_data` and `delete_user_data`, wired to `auth.user.deleted`.

## Step 8: port the web binding

- `module.web.ts` calls `defineModule` with lazy routes (public, member, admin) and slots.
- Data only through the generated client and TanStack Query.
- Styles only from tokens; kernel UI kit first.
- Components other modules may use go in `web/public.ts` and nowhere else.
- Keep business logic out of the binding so desktop and mobile bindings can reuse the API later.

## Step 9: tests

- Port the source's tests where they test behavior; drop ones that test the old structure.
- Add HTTP contract tests that don't import the module's Python (they will judge a future TypeScript port too).
- Test every permission path and every re-implemented RLS policy or trigger from step 4.
- Migration round trip on an empty and a seeded database.
- Component tests per page, one Playwright smoke per route, axe with no serious violations, and the server-copy test for public pages.
- A bug found while porting gets a test seen failing before the fix.

## Step 10: docs and the gate

- `MODULE.md` sections: what it does; use when and avoid when; what it adds (routes, tables, slots, permissions, events); settings and env vars; install notes; extension points; known limits; source and license.
- Generate `openapi.json`, regenerate `catalog.json`, start `CHANGELOG.md`.
- Run the spec's quality gate (section 16). Promote `status` to `stable` only when every row passes in CI.

## Extraction report

Put this in the PR description:

```markdown
## Module: <id> <version>
**Source:** <project> @ <commit>, <paths>. Runners-up: <projects, why not>.
**Provenance:** owner's code: yes. Brand check: <pass/n.a.>. Data and secrets stripped: yes.
**Replaced with kernel:** <list>
**Re-implemented protections:** <each RLS policy, trigger, middleware, and its test>
**Dropped:** <what and why>
**New dependencies:** <package: reason>
**Gate:** <each row: pass/fail, with the command run>
**Known limits:** <list>
```

## Pitfalls

- RLS or middleware protections lost in the port.
- Hidden coupling: a direct import of another feature that should be an event.
- The source's branding, copy, domains or fixtures carried along.
- Hard-coded colors, numbers or provider ids instead of tokens and settings.
- GET routes with side effects, and work done inside webhook requests instead of jobs.
- Calling a module `stable` before its gate passes.