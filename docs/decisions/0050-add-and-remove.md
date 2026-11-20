# 0050: `mechframe add` and `remove`: what each writes, what `remove` keeps, and how `requires` reads a range

- **Date:** 2026-11-20
- **Status:** Decided; applied in K5.4 (#94).
- **Context:** K5.4 builds `add`, `remove` and `new --recipe` (the K5 contract §2 and §4 item 4) on fixture modules, since no module is built yet. SPEC 12 lists `add`'s steps and says `remove` keeps a module's tables. Building them had to settle:
  - where a module's settings go besides `.env.example`: an apply of `.railway/railway.ts` deletes a variable on the service that the file doesn't list (decision 0048);
  - what keeps the database's Alembic version readable once a module's files are gone;
  - how `requires` ranges read, with the kernel at `0.1.0-dev.0` and every module requiring `^0.1`;
  - what a recipe does with its modules' order and its `settings`.
- **Decision:**
  1. **`add <id>`** refuses, before writing anything:
     - a module already in the site, or one the checkout hasn't built (planned, a scaffold or none), or whose manifest doesn't validate;
     - a kernel or a required module whose version its range doesn't meet, or a range it can't read;
     - a required module the site doesn't have (it names the `add` to run first);
     - a conflict, either module's: the new one's `conflicts`, or one in the site that names it;
     - a setting the site sets already (in `.env.example` or another module's manifest);
     - files where the module goes that the lock doesn't record.

     Then it copies the module, writes both registries whole from the lock's modules (in id order, as the harness finds its own), appends the module's settings to `.env.example` as a block of its own, adds each to `railway.ts` as `preserve()` in a `// <id>` group, and records its version, the day and every file's hash in the lock. It prints the settings still to set, `python -m app.migrations upgrade <id>@head` when it has migrations, and the site's tests.
  2. **`remove <id>`** refuses while another module in the site requires it. It removes the module's backend package (with its manifest) and its web folder, edited and added files too, and names those. It rewrites the registries, comments its settings out in `.env.example`, and drops its lock entry. It keeps:
     - its tables;
     - **its migrations** in `backend/migrations/<id>/`: the database's `alembic_version` still names the module's revision, and Alembic stops on a revision it can't find. `--drop-data`, later, runs their downgrade first;
     - **its `railway.ts` lines,** so an apply keeps what the owner typed into Railway. Deleting them makes the next apply remove those variables, which the plan marks as destructive.

     A later `add` writes the block in `.env.example` again, overwrites the migrations with the checkout's, and adds no `railway.ts` line twice.
  3. **Each runs whole or not at all:** a journal keeps what every file held, and a failure half-way puts it back. A run holds the site by `.mechframe-busy`, so two never mix.
  4. **Ranges** (`mechframe.ranges`): `^`, `~`, an exact or partial version, `>=`, `>`, `<=`, `<`, `*`, and comparators separated by spaces, all of which must hold. No `||`. A pre-release meets a range from the lowest pre-release of each lower bound: the kernel `0.1.0-dev.0` meets `^0.1` (`>=0.1.0-0 <0.2.0-0`), and `0.2.0-dev.0` doesn't.
  5. **`new --recipe <id>`** checks the recipe before writing anything: it validates; every module is built, or they're listed; each module's requirements are in the recipe; no two conflict. It makes the kernel's site, then runs `add` for each module after the ones it requires. A failure in any of them takes the whole site away. The theme is `--theme`, else the recipe's. The recipe's `settings` are printed for Admin, Settings: nothing applies them before the site runs.
- **Alternatives:**
  - *Removing a module's migrations with its code:* the next `upgrade` would stop on the revision `alembic_version` names. Clearing that row needs the database, which the CLI never touches.
  - *Removing its `railway.ts` lines, as SPEC 12's "undo" reads:* the next apply would delete the variables the owner typed in, keys among them, for a module that might come back.
  - *`add` pulling in the modules a module requires:* an agent couldn't see what it was agreeing to. The refusal names the one `add` to run first.
  - *Strict semver ranges, pre-releases left out:* no module could be added until the kernel's first release.
- **Consequences:**
  - The two registries and the lock can't drift: both registries are written from the lock every time.
  - A removed module's migrations still run on a new database made for the site. They make its tables, which nothing reads. `--drop-data` is the way out.
  - `mechframe check` doesn't look at a removed module's kept migrations: no lock entry records them.
  - SPEC 12 gains `railway.ts` in step 4, and the kept migrations and lines in `remove`.
- **See:** SPEC 5, 12 and 13; decisions 0047, 0048 and 0049; the K5 contract's change 8; `cli/mechframe/modules.py`, `settings.py`, `registries.py` and `ranges.py`; `cli/tests/fixtures/`
