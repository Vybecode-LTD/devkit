# Skill backlog

The owner's rule (2026-11-12): keep a running list of skill ideas and build them all together at the end, unless one is needed to keep the project moving. Add every new idea here as it comes up, with the date and whether it blocks anything.

## Built

Account copies are saved by the owner from the review cards Claude proposes; `skills/` holds the DevKit-specific ones in the repo too.

| Skill | Built | Where |
| --- | --- | --- |
| `devkit-module-extractor` | 2026-11-12 | `skills/` and the owner's account |
| `devkit-site-picker` | 2026-11-12 | `skills/` and the owner's account |
| `beat-license-generator` | 2026-11-12 | `skills/` and the owner's account |
| `printful-v2-adapter` | 2026-11-12 | `skills/` and the owner's account |
| `alembic-multi-module-migrations` | 2026-11-12 | `skills/` and the owner's account |
| `module-contract-lint` | 2026-11-12 | `skills/` and the owner's account; absorbs `fastapi-route-audit` |
| `server-copy-for-crawlers` | 2026-11-12 | The owner's account |
| `auth-threat-model-checklist` | 2026-11-12 | The owner's account |
| `spec-to-kickoff` | 2026-11-12 | The owner's account |
| `supabase-rls-to-fastapi` | 2026-11-12 | The owner's account |
| `doc-and-repo-spec-sync` | 2026-11-12 | The owner's account |
| `pytest-throwaway-postgres` | 2026-11-12 | The owner's account |
| `conditional-settings-saves` | 2026-11-12 | The owner's account |
| `path-filtered-ci` | 2026-11-12 | The owner's account |
| `remote-device-git-sync` | 2026-11-12 | The owner's account |

**Updated 2026-11-12:** the account copy of `devkit-module-extractor` now uses `backend/<id_>/` (the id with hyphens turned into underscores) and decision 0009's fixed names.

## Waiting to be built

| Skill | What it would do | Raised | Blocks anything? |
| --- | --- | --- | --- |
| `devkit-auth-contract-tests` | Turns SPEC.md 14.13 into a ready pytest and httpx suite any site can run | 2026-11-12 | No. Waits until K2 makes the suite in `kernel/tests/contract/` pass, so the skill packages tested code |
| `contract-test-mutant-check` | Proves a test suite can fail: plants one mutant per rule (a dropped index, a removed check, a skipped guard), runs the suite against each, and lists the mutants nothing caught. The audit did this by hand for the migration snapshot (11 of 11 unseen) and the contract suite | 2026-11-12 | No |
| `fastapi-route-introspection` | Walks a FastAPI 0.16x app's routes through `iter_route_contexts`, full paths and templates included, for audits, rate-limit keys and access logs; covers the traps (included routers kept whole, mounts, websockets) | 2026-11-12 | No |
| `bundled-data-licence-audit` | Checks each bundled third-party dataset's own terms against NOTICE (a collection's licence isn't its files'), pins the source commit and blob ids, and makes the rebuild byte-for-byte reproducible | 2026-11-12 | No |
| `review-bot-triage` | Reads the review bots' comments on merged PRs (Codex, CodeRabbit), reproduces each claim with a failing test, and turns the real ones into follow-up PRs. Four of four were real in this audit | 2026-11-12 | No |
| `postgres-catalog-snapshot` | A pg_catalog snapshot (columns, indexes, constraints, types, functions, sequences, triggers, rows) for migration round trips, with its mutant controls | 2026-11-12 | No. Could fold into `alembic-multi-module-migrations` |

## Dropped

| Skill | Why | Date |
| --- | --- | --- |
| `devkit-module-contract` | `modules/_template/`, `devkit-module-extractor` and `module-contract-lint` cover it | 2026-11-12 |
| `fastapi-route-audit` | Folded into `module-contract-lint` | 2026-11-12 |
