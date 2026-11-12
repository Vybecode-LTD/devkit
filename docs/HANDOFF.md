# Handoff

Overwritten every session. 2026-11-12.

## State

- `SPEC.md` v0.1 is written, with the owner's answers to Q1 to Q11 and the changes from the Vibrant Mindz plan. The design doc "AI DevKit Spec v0.1" mirrors it.
- Repo scaffold only: schemas, module template, recipes, decisions 0001 to 0008, four project skills. No code, no git history, no remote.
- First real site: the new Vibrant Mindz site (`docs/plans/vibrant-mindz-module-plan.md`).

## Next

1. `KICKOFF.md` phase K0: git init, Python and web tooling, Alembic with per-module branches, CI, the brand check. Ask the owner before creating the GitHub repo.
2. K1: core infrastructure lifted from VybeSite.
3. K2: auth to SPEC.md section 14, contract tests first.

## Blockers

None. The GitHub repo waits on the owner's go-ahead.

## Warnings

- Nothing from the client folder named in `docs/private/README.md`, and nothing from VybeSite's `dev plans\` or `snapshots\`. Run VybeSite's brand check on lifted code.
- VybeSite's sessions (JWT) and account tables (staff and members split) differ from the spec. Port the behavior, not the shape.
- Module Python packages and tables use the id with hyphens turned into underscores.
