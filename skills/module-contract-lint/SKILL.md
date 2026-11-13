---
name: module-contract-lint
description: Check an AI DevKit module (or the kernel) against the module contract before it merges or is copied into a site. Covers the manifest schema, folder layout, package and table naming, every route declaring public, member or permission access, no cross-module imports except listed public surfaces, token-only styles, data hooks and the quality gate. Use when reviewing a module PR, finishing an extraction, or when a site's devkit check fails.
---

# Module contract lint

A module is only reusable if it keeps the contract (SPEC.md sections 4 to 16). This is the checklist and the commands that prove each point. Run it from the DevKit repo root, or from a site whose modules were copied in. Where the spec has changed since this skill was written, the spec wins.

Report every row as pass or fail with the command or file that shows it. A row that can't be checked yet (the CLI isn't built, the module has no web binding) is "not applicable", with the reason. Never mark a row passed by reasoning about code you haven't run.

## 1. The manifest

- `python -m tools.validate_schemas` passes. It checks every `module.json` against `schema/module.schema.json`, plus:
  - the folder is named by the id;
  - the backend package is the id with `-` turned into `_`;
  - every table starts with `<id_>_`;
  - every permission and notification key starts with `<id>.`.
- `use_when` holds 2 to 4 concrete sentences an agent can match against a brief. `avoid_when` names the better choice.
- `requires.modules` lists every module whose `public.py` or `web/public.ts` this module imports, and nothing else.
- `data_hooks.export` and `delete` are true when any table references `auth_user`.
- `source` names the project, the commit and the license.

## 2. Folder layout

```
modules/<id>/module.json MODULE.md CHANGELOG.md
  backend/<id_>/ models.py schemas.py service.py router.py [events.py jobs.py server_copy.py public.py]
  migrations/     its own Alembic branch
  web/            module.web.ts api.ts public.ts pages/ components/
  tests/          backend/ web/ e2e/ contract/
```

The kernel finds a module by fixed names (decision 0009): `router.py`'s `router`, `schemas.py`'s `Settings` (every field defaulted; secrets typed `SecretStr`), and `__init__.py`'s `CSP` list of (directive, https origin).

## 3. Routes declare their access

Every route under `/api/` must carry `Depends(public)`, `current_user`, `optional_user` or `require_permission(...)`. The kernel's audit finds the ones that don't:

```python
from kernel.access import undeclared
assert undeclared(app) == []          # also served by the harness at GET /api/_test/routes
```

FastAPI 0.16x keeps included routers whole in `app.routes`, so walk them with `fastapi.routing.iter_route_contexts(app.routes)`. Each context has `.path`, `.methods` and `.dependant` with the router-level dependencies applied. A loop over `app.routes` alone misses every module route.

Also check:
- nothing changes state on GET;
- admin routes live under `/api/<id>/admin`;
- errors are `Problem("<id>.<snake_case>", status, detail)`, never a bare `HTTPException` with a string;
- lists are cursor-paginated (`?cursor=&limit=`, at most 100, `{items, next_cursor}`).

## 4. Boundaries

- No import of another module's package except `<other>.public`, and only when `<other>` is in `requires.modules`. List the other modules' package names, then:
  `grep -rnE "^\s*(from|import) (blog|shop|comments)\b" modules/<id>/backend` (your names in the group). Every hit must be `<other>.public`.
- Imports from the kernel come only from `kernel` (its `__init__`), never `kernel.<private module>`.
- No foreign key into another module's tables (read the migrations).
- The web binding imports only `@/kernel` and other modules' `public.ts`; no business logic in it.

## 5. Data and security

- Bodies are Pydantic in strict mode; no `dict` parameters.
- Secrets live in `Settings` as `SecretStr` (sealed by the kernel) or in env vars, never in the repo or the logs.
- Outbound HTTP has a timeout, and any URL a user supplied goes through the SSRF guard.
- Third-party hosts enter the CSP only through the module's `CSP` list.
- Personal data: `export_user_data` and `delete_user_data` exist, are tested, and handle `auth.user.deleted`.
- Records that grow declare a retention period.

## 6. Front end

- Colours, spacing and radii come only from theme tokens: `grep -rnE "#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(" modules/<id>/web` finds nothing.
- `defineModule` admin routes start with `/admin/` and name a permission.
- Every page has a component test.

## 7. The quality gate (SPEC.md section 16)

```
python -m ruff check modules/<id> && python -m black --check modules/<id>
python -m mypy modules/<id>/backend
python -m pytest modules/<id> --cov=modules/<id>/backend --cov-fail-under=85
npm run lint && npm run typecheck && npm test
```

Then the migration round trip, the contract tests (HTTP only, no imports of the module's Python), Playwright smoke and axe for each route, the server-copy test for public pages, and gitleaks and pip-audit clean. For any code lifted from VybeSite, the brand check must pass too.

## Report

```markdown
## Contract lint: <id> <version>
| Area | Result | Evidence |
| --- | --- | --- |
| Manifest | pass | validate_schemas: 0 problems |
| Routes declare access | fail | POST /api/<id>/import has none |
...
**Blocking:** <rows that fail>  **Follow-ups:** <non-blocking notes>
```
