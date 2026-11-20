# 0047: The CLI and the site template: copied from the checkout, a site's exact layout, hashes that ignore line endings, and what waits

- **Date:** 2026-11-20
- **Status:** Decided; applied in K5 from #91
- **Context:** K5 builds `mechframe` and `templates/site/` (KICKOFF K5; contract `dev plans/contracts/k5-cli-and-site-template.md`, approved 2026-11-20). SPEC 4, 12 and 13 sketched the site's tree, the commands and the lock, and left out:
  - where the CLI copies from;
  - where a module's Python package and each migration branch sit in a site;
  - how a hash survives Git's line endings;
  - what `advisories.json` holds;
  - how `add` runs migrations and tests in a site whose Python isn't the CLI's.

  No module is built yet, so `diff` and `upgrade` have nothing to compare.
- **Decision:**
  1. **The CLI copies from, and checks against, the checkout its own code sits in.** It fetches nothing. It runs as `python -m mechframe`, or as `mechframe` and `mf` after `python -m pip install -e .`, the one part of the repo that is installed.
  2. **A site's layout is exact** (SPEC 4):
     - The kernel's package goes to `backend/kernel/`, with `kernel.json`.
     - Its migrations go to `backend/migrations/kernel/`, and its web to `web/src/kernel/`.
     - A module's package goes to `backend/modules/<id_>/`, with its manifest and docs. Its migrations go to `backend/migrations/<id>/`, and its web to `web/src/modules/<id>/`.
     - Tests, caches and the web folders' package files stay behind.
  3. **A lock records each file's `sha256:` with `\r\n` read as `\n`,** so a Windows checkout isn't an edit.
  4. **`check` exits 2 when the lock or a copied manifest doesn't validate,** 1 on an open high or critical advisory, and 0 otherwise. Edits and versions behind are reported.
  5. **`advisories.json`'s entries** are `{id, module, introduced, fixed, severity, summary}` (`schema/advisories.schema.json`). A copy is affected from `introduced` up to, but not including, `fixed`.
  6. **`add` does SPEC 12's steps 1 to 5 and prints 6 and 7** (migrations, tests) for the site's own environment.
  7. **The owner's answers** (2026-11-20, each as recommended):
     - `diff` and `upgrade` wait for a module's second version;
     - `create-owner` prints a one-time link to set a password;
     - Railway gets `FORWARDED_ALLOW_IPS=*`;
     - a site's own pages join in K5 (`mountApp({ site })`, `create_app(site=...)`);
     - the template ships a CI workflow that runs `mechframe check` from a shallow clone of `mechframe/mechframe`.
- **Alternatives:**
  - *Source:* download a tagged release (needs a registry and a release process; decision 0002 copies at build time).
  - *Layout:* keep SPEC 4's `backend/modules/<id>/` (a hyphenated id can't be imported).
  - *Hashes:* of the raw bytes (every Windows checkout reads as edited).
  - *`add`:* run migrations and tests itself (it would need the site's interpreter and database).
- **Consequences:**
  - A site is made where MechFrame is checked out. A site's CI clones MechFrame to run `check`, which works while the repo is public (decision 0011).
  - `remove --drop-data` waits for the first module with data: its downgrade must run before its files go.
  - A module's own Python or npm packages have no place in the manifest yet: they're added with the first module that needs one.
- **See:** SPEC 4, 12, 13 and 17; decisions 0002, 0009, 0011 and 0034; `cli/mechframe/`; `schema/advisories.schema.json`
