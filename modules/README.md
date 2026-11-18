# Modules

One folder per module, laid out exactly as SPEC.md section 4 shows. Copy `_template/` to start a new one, or follow the `mechframe-module-extractor` skill to lift one from another project.

- The folder name is the module id (lowercase letters, digits and hyphens).
- The Python package under `backend/` is the id with hyphens turned into underscores: `print-on-demand` has `backend/print_on_demand/`.
- `module.json` must validate against `schema/module.schema.json`.
- A module is `experimental` until it passes every row of the quality gate (SPEC.md section 16) in CI.
- A folder starting with `_` is not a module: the harness skips it. Besides `_template/`, the Vibrant Mindz scaffolds wait here as `_<id>/` until each is built, with its first migration and tests, and renamed (`docs/plans/vibrant-mindz-backend/KICKOFF.md`). mypy, ESLint, `tsc` and the schema check still cover them.
