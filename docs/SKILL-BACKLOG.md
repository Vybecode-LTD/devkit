# Skill backlog

The owner's rule (2026-11-12): keep a running list of skill ideas and build them all together at the end, unless one is needed to keep the project moving. Add every new idea here as it comes up, with the date and whether it blocks anything.

## Built

| Skill | Built | Where |
| --- | --- | --- |
| `devkit-module-extractor` | 2026-11-12 | `skills/` and the owner's account |
| `devkit-site-picker` | 2026-11-12 | `skills/` and the owner's account |
| `beat-license-generator` | 2026-11-12 | `skills/` and the owner's account |
| `printful-v2-adapter` | 2026-11-12 | `skills/` and the owner's account |

**Pending update:** the account copy of `devkit-module-extractor` says `backend/<id>/`. The spec now uses the id with hyphens turned into underscores for the Python package (`backend/print_on_demand/`). The copy in `skills/` already has the fix; update the account copy in the next batch.

## Waiting to be built

| Skill | What it would do | Raised | Blocks anything? |
| --- | --- | --- | --- |
| `alembic-multi-module-migrations` | One Alembic branch per module that depends on the kernel's head; `version_locations`; merging heads; upgrade, downgrade, upgrade tests | 2026-11-12 | No. KICKOFF K0 and K1 cover the setup inline |
| `module-contract-lint` | Checks a module against the contract: manifest schema, folder layout, token-only styles, every route's declared access, no cross-module imports | 2026-11-12 | No. Its checks also become part of `devkit check` in K5 |
| `devkit-module-contract` | A fill-in template for starting a module | 2026-11-12 | No. Mostly covered by `modules/_template/` and the extractor; may be dropped |
| `server-copy-for-crawlers` | VybeSite's plain-HTML-for-crawlers pattern (head tags, page words, JSON-LD, real 404s) for any React site | 2026-11-12 | No |
| `auth-threat-model-checklist` | A security checklist run on every auth change | 2026-11-12 | No. SPEC.md 14.13 holds the test list |
| `devkit-auth-contract-tests` | Turns SPEC.md 14.13 into a ready pytest and httpx suite any site can run | 2026-11-12 | No. K2 writes these tests in the kernel first; the skill packages them after |
| `spec-to-kickoff` | Turns a spec doc into a Claude Code kickoff prompt plus a build checklist | 2026-11-12 | No |
| `supabase-rls-to-fastapi` | Rewrites Supabase row-level-security policies and triggers as server-side checks and event handlers, each with a test | 2026-11-12 | No. Needed before porting Brewr's forum or other Supabase projects |
| `doc-and-repo-spec-sync` | Keeps a design doc and its Markdown copy in a repo (such as `SPEC.md`) in step, with the change log and decision records | 2026-11-12 | No |
| `pytest-throwaway-postgres` | The fixture set from `conftest.py`: one database per run, an empty one per migration test, skip without a server unless CI requires it, asyncpg plus pytest-asyncio on one loop | 2026-11-12 | No. The kernel's `conftest.py` is the working copy |
| `conditional-settings-saves` | Versioned settings with a three-way merge per field, secrets typed-only, an advisory lock and a 409 with both values (VybeSite's pattern, generalized in `kernel/settings.py`) | 2026-11-12 | No |
| `path-filtered-ci` | A GitHub Actions workflow whose jobs run only for the paths they check, with a single "CI result" gate a ruleset can require (VybeSite's and DevKit's `ci.yml`) | 2026-11-12 | No |
| `fastapi-route-audit` | Lists every route that declares no access, walking FastAPI 0.16x's included routers with `iter_route_contexts` | 2026-11-12 | No. `kernel/access.py` does it for DevKit |
