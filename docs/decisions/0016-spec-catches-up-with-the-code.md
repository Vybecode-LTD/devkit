# 0016: The spec catches up with the code

- **Date:** 2026-11-12
- **Status:** Applied
- **Context:** The audit of 2026-11-12 found the spec saying less than the code, or something else (findings F23, F24, F48, F51). Three PRs brought it in line, and a review pointed out that none of them carried its own decision record, as CLAUDE.md asks of every spec change. This record covers them.
- **Decision:**
  - **Section 4:** a module's layout is the template's. `backend/<id_>/` lists `__init__.py` (it holds `CSP`). `web/` is `module.web.ts api.ts public.ts pages/ components/`, and routes are defined in `module.web.ts`. There's no `routes.tsx`.
  - **Section 5:** the manifest's `settings` is a summary for agents. The `Settings` model is the source of truth, and `devkit check` holds the summary to it.
  - **Section 6:** the backend table lists what `kernel/__init__.py` exports, with a "Since" column for names to come. A second table covers what sites use.
  - **Section 7:** the fixed discovery names, the problem `type` (`urn:devkit:problem:<code>`) and the secret-field rules.
  - **Section 15:** the seven CSP directives a module may open, under module switches only, with no wildcard in `script-src`.
  - **14.8:** the kernel's own permissions are declared in `kernel/kernel.json`. A test holds the auth migration's seed to that list, and the seed stays in the migration, which mustn't read a file that changes after it ships.
- **Alternatives:** Changing the code to match the old text. That was wrong in each case: no `routes.tsx` exists, a settings flag in the manifest would be a second source of truth, and a per-setting CSP has no use yet.
- **Consequences:** The claude.ai Spec doc needs sections 4 to 7, 14.8, 15 and the change log synced.
- **See:** SPEC.md 4 to 7, 14.8 and 15; decisions 0009 and 0015; `kernel/kernel.json`
