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

## Dropped

| Skill | Why | Date |
| --- | --- | --- |
| `devkit-module-contract` | `modules/_template/`, `devkit-module-extractor` and `module-contract-lint` cover it | 2026-11-12 |
| `fastapi-route-audit` | Folded into `module-contract-lint` | 2026-11-12 |
