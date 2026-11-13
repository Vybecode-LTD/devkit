---
name: alembic-multi-module-migrations
description: Set up and work with Alembic when a FastAPI app is built from a kernel plus copied-in modules, each owning its own migration branch. Use when adding a module's first migration, wiring version_locations, labelling branches, making a module depend on the kernel's head, merging heads, autogenerating against several metadata sources, or writing the upgrade-downgrade-upgrade and model-drift tests. Built from AI DevKit's harness (harness/migrations.py, harness/alembic/env.py).
---

# Alembic with one branch per module

One database, many owners: the kernel has a migration branch, and every module copied into the site has its own. Each branch moves on its own, and `upgrade heads` runs them all in dependency order. This is how AI DevKit (SPEC.md section 10) does it; the same shape fits any plugin-style app.

## The layout

```
kernel/migrations/            branch "kernel": 0001_kernel_core.py, 0002_auth_tables.py
modules/<id>/migrations/      branch "<id>": its own revisions
harness/alembic/env.py        the one environment (a site: backend/alembic/env.py)
harness/migrations.py         builds the Alembic Config in code
```

There is no `alembic.ini` to keep in sync: the config is built in code, so a module added to the folder is picked up without editing a file.

```python
cfg = Config(stdout=sys.stdout)            # read stdout now: Alembic binds its default at import
cfg.set_main_option("script_location", str(ROOT / "harness" / "alembic"))
cfg.set_main_option("path_separator", "os")          # Alembic 1.16+: replaces version_path_separator
cfg.set_main_option("version_locations", os.pathsep.join(str(p) for p in migration_dirs()))
cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))   # ini syntax: double any %
```

`migration_dirs()` = the kernel's folder, then each module folder that has `migrations/`, skipping folders that start with `_` (the template).

## env.py

- Import every model before reading `Base.metadata`. Load the kernel's models, then each module's `<package>.models`, where the package name is the module id with hyphens turned into underscores. Autogenerate only sees tables whose models were imported.
- One async engine with `NullPool`, `connection.run_sync(...)` inside `asyncio.run(...)`.
- `context.configure(..., compare_type=True, compare_server_default=True, transaction_per_migration=True)`.
- Because env.py calls `asyncio.run`, never call `command.upgrade` from inside a running event loop. In async tests use `await asyncio.to_thread(upgrade, url)`.

## A branch's first revision

```python
revision = "blog_0001"
down_revision = None
branch_labels = ("blog",)
depends_on = "kernel_0002"     # the kernel revision whose tables this module needs (auth_user)
```

- Name revisions `<branch>_<NNNN>` and files `NNNN_<what>.py`, so ids are readable in `alembic heads`.
- `depends_on` names a revision id, not `kernel@head`: pin the oldest kernel revision the module really needs, so a new kernel migration never re-orders module history.
- Later revisions of the module: `down_revision = "blog_0001"`, no labels.
- Make one with the head pinned to the branch, so it never lands on another module's chain:
  `command.revision(cfg, message="...", autogenerate=True, rev_id="blog_0002", head="blog@head", version_path=".../modules/blog/migrations")`
- Then read the generated file. Strip the "auto generated" comments, add the docstring saying what and why, set `destructive = True` if it drops or rewrites data, and seed rows with `op.bulk_insert`.

## Ownership rules (enforce them in review)

- Table names start with the owner's prefix: `kernel_`, `auth_`, `<id_>_`.
- A module's foreign keys point only at its own tables and the kernel's (`auth_user`). Never at another module's: store the id and listen for the other module's delete event.
- A migration that adds a constraint checks existing rows first and stops with the fix, rather than deleting data to fit.
- Autogenerate misses enum value additions and some server-default changes: write those by hand. A `downgrade()` that drops a table using an enum also drops the type.

## The two tests every repo needs

```python
async def test_upgrade_downgrade_upgrade(empty_database_url):
    await asyncio.to_thread(upgrade, empty_database_url)
    first = await schema_of(empty_database_url)          # {table: [columns]}
    await asyncio.to_thread(downgrade, empty_database_url)   # to "base"
    assert await schema_of(empty_database_url) == {}
    await asyncio.to_thread(upgrade, empty_database_url)
    assert await schema_of(empty_database_url) == first

async def test_models_match_the_migrations(empty_database_url):
    await asyncio.to_thread(upgrade, empty_database_url)
    # run_sync: compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
```

Add a third that walks `ScriptDirectory.from_config(cfg).walk_revisions()`. It checks that every base revision (no `down_revision`) in `kernel/migrations` is labelled `kernel`, that each module base is labelled with its module id, and that each module base has `depends_on` set.

## Merging and removing

- Two heads on one branch (two PRs each added a revision) → `command.merge(cfg, ["blog_0003", "blog_0004"], message="merge", branch_label=None)` inside that branch's folder.
- Removing a module keeps its tables unless the owner asks to drop data: run `downgrade <id>@base` first, and only then delete the folder.
- Upgrade one module alone: `upgrade <id>@head`. See every branch: `heads --verbose`, `history`.

## Pitfalls

- A module folder with an `__init__.py` in `migrations/` makes Alembic import it as a package. Keep migration folders plain.
- `version_locations` with spaces in paths and the old space separator: always set `path_separator=os`.
- Generating a revision without `head="<branch>@head"` attaches it to whichever head Alembic picks.
- Tests that share one database across runs hide downgrade bugs: give the round-trip test an empty database of its own.
