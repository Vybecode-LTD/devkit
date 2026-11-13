"""Every migration round-trips, and the models match what the migrations make
(SPEC.md sections 10 and 16; KICKOFF.md K0 step 7).

- Upgrade, downgrade, upgrade, on an empty database and on one holding a row
  in every table, leaves the same catalog: columns with their types,
  nullability and defaults, indexes, constraints, types, functions,
  sequences, triggers, views and the seeded rows.
- Each revision steps down and back up on its own (the stairway).
- After the upgrade, and again after a second one, the models and the
  database agree, compared as `alembic check` compares them.
- The kernel's first revision is labelled `kernel`. Each module's first
  revision is labelled with its id and depends on the kernel.
- The catalog itself sees each kind of change a bad downgrade could leave.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import column, inspect, select, text
from sqlalchemy import table as table_
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from harness.layout import KERNEL, module_dirs
from harness.migrations import config, downgrade, upgrade
from harness.models import load_all
from kernel.db import Base, async_database_url


async def _sync(url: str, work: Any) -> Any:
    engine = create_async_engine(async_database_url(url))
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(work)
    finally:
        await engine.dispose()


_CATALOG = {
    "columns": """
        SELECT table_name, column_name, data_type, udt_name, is_nullable,
               column_default, character_maximum_length, numeric_precision
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name <> 'alembic_version'""",
    "indexes": """
        SELECT tablename, indexname, indexdef FROM pg_indexes
        WHERE schemaname = 'public' AND tablename <> 'alembic_version'""",
    "constraints": """
        SELECT c.relname, con.conname, con.contype, pg_get_constraintdef(con.oid)
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname <> 'alembic_version'""",
    "types": """
        SELECT t.typname, t.typtype,
               (SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
                FROM pg_enum e WHERE e.enumtypid = t.oid)
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        LEFT JOIN pg_class c ON c.oid = t.typrelid
        WHERE n.nspname = 'public'
          AND (t.typtype IN ('e', 'd', 'r', 'm') OR (t.typtype = 'c' AND c.relkind = 'c'))""",
    "functions": """
        SELECT p.proname, pg_get_function_identity_arguments(p.oid), md5(p.prosrc)
        FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'""",
    "sequences": """
        SELECT sequencename, data_type, start_value, increment_by FROM pg_sequences
        WHERE schemaname = 'public'""",
    "triggers": """
        SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid)
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND NOT t.tgisinternal""",
    "views": "SELECT viewname, definition FROM pg_views WHERE schemaname = 'public'",
    "extensions": "SELECT extname FROM pg_extension WHERE extname <> 'plpgsql'",
}
#: Column types left out of the rows: they differ on every upgrade.
_MOMENTS = {"timestamp with time zone", "timestamp without time zone", "date"}


def _catalog(connection: Connection) -> dict[str, Any]:
    """Everything a migration makes, and the rows in every table."""
    found: dict[str, Any] = {
        name: sorted(tuple(map(str, row)) for row in connection.execute(text(query)))
        for name, query in _CATALOG.items()
    }
    rows: dict[str, list[tuple[str, ...]]] = {}
    for table in sorted(inspect(connection).get_table_names()):
        if table == "alembic_version":
            continue
        columns = [
            column["name"]
            for column in inspect(connection).get_columns(table)
            if str(column["type"]).lower() not in _MOMENTS
            and not str(column["type"]).upper().startswith("TIMESTAMP")
        ]
        query = select(*(column(name) for name in columns)).select_from(table_(table))
        rows[table] = sorted(tuple(map(str, row)) for row in connection.execute(query))
    found["rows"] = rows
    return found


def _empty(connection: Connection) -> bool:
    found = _catalog(connection)
    return not found.pop("rows") and not any(found.values())


def _drift(connection: Connection) -> list[Any]:
    """`alembic check`, with the options the environment uses (env.py)."""
    load_all()
    context = MigrationContext.configure(
        connection, opts={"compare_type": True, "compare_server_default": True}
    )
    return list(compare_metadata(context, Base.metadata))


USER = uuid.UUID(int=1)
_SEED = [
    "INSERT INTO auth_user (id, email, email_normal, password_hash) "
    "VALUES (:user, 'Ana@Site.test', 'ana@site.test', 'x')",
    "INSERT INTO auth_role (id, name) VALUES ('writer', 'Writer')",
    "INSERT INTO auth_role_permission (role_id, permission) VALUES ('writer', 'blog.write')",
    "INSERT INTO auth_user_role (user_id, role_id, granted_by_id) VALUES (:user, 'writer', :user)",
    "INSERT INTO auth_permission_override (id, user_id, permission, resource_type, resource_id, "
    "effect) VALUES (gen_random_uuid(), :user, 'blog.edit', 'post', '1', 'deny')",
    "INSERT INTO auth_identity (id, user_id, provider, subject) "
    "VALUES (gen_random_uuid(), :user, 'github', '42')",
    "INSERT INTO auth_passkey (id, user_id, credential_id, public_key, name) "
    "VALUES (gen_random_uuid(), :user, '\\x01', '\\x02', 'Laptop')",
    "INSERT INTO auth_totp (user_id, secret_sealed) VALUES (:user, 'sealed')",
    "INSERT INTO auth_recovery_code (id, user_id, code_hash) "
    "VALUES (gen_random_uuid(), :user, 'h1')",
    "INSERT INTO auth_session (id, user_id, token_hash, epoch, role_version, started_at, "
    "last_seen_at, expires_at, authenticated_at) "
    "VALUES (gen_random_uuid(), :user, 's1', 0, 0, now(), now(), now(), now())",
    "INSERT INTO auth_token (id, purpose, token_hash, email_normal, created_at, expires_at) "
    "VALUES (gen_random_uuid(), 'sign_in_code', 't1', 'ana@site.test', now(), now())",
    "INSERT INTO auth_api_key (id, key_id, mode, user_id, name, secret_hash) "
    "VALUES (gen_random_uuid(), 'k1', 'live', :user, 'CI', 'h')",
    "INSERT INTO auth_audit_event (actor_id, action, result, ip) VALUES (:user, 'x', 'ok', '203.0.113.9')",
    "INSERT INTO kernel_module_state (module_id, enabled, updated_by_id) VALUES ('blog', false, :user)",
    "INSERT INTO kernel_setting (module_id, version, updated_by_id) VALUES ('blog', 1, :user)",
    "INSERT INTO kernel_setting_version (id, module_id, number, values, changed, via, saved_by_id) "
    "VALUES (gen_random_uuid(), 'blog', 1, '{}', '[]', 'form', :user)",
]


def _seed(connection: Connection) -> None:
    for statement in _SEED:
        connection.execute(text(statement), {"user": USER})
    connection.commit()


async def test_upgrade_downgrade_upgrade(empty_database_url: str) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    first = await _sync(empty_database_url, _catalog)
    assert first["rows"]["auth_role"], "the built-in roles are seeded"
    await asyncio.to_thread(downgrade, empty_database_url)
    assert await _sync(empty_database_url, _empty)
    await asyncio.to_thread(upgrade, empty_database_url)
    assert await _sync(empty_database_url, _catalog) == first


async def test_upgrade_downgrade_upgrade_with_a_row_in_every_table(
    empty_database_url: str,
) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    first = await _sync(empty_database_url, _catalog)
    await _sync(empty_database_url, _seed)
    seeded = await _sync(empty_database_url, _catalog)
    unseeded = sorted(table for table, rows in seeded["rows"].items() if not rows)
    assert unseeded == [], f"_SEED gives these tables no row: {unseeded}"
    await asyncio.to_thread(downgrade, empty_database_url)
    assert await _sync(empty_database_url, _empty)
    await asyncio.to_thread(upgrade, empty_database_url)
    assert await _sync(empty_database_url, _catalog) == first


def _revisions() -> list[Any]:
    """Every revision, each after the ones it builds on."""
    return list(reversed(list(ScriptDirectory.from_config(config()).walk_revisions())))


async def test_each_revision_steps_down_and_back_up(empty_database_url: str) -> None:
    """The stairway: up one, down one, up again, and the catalog at each step
    matches the one before it."""
    below = await _sync(empty_database_url, _catalog)
    for revision in _revisions():
        if isinstance(revision.down_revision, tuple):
            pytest.fail(f"{revision.revision} merges heads: give the stairway a merge step")
        down = revision.down_revision or (
            f"{next(iter(revision.branch_labels))}@base" if revision.branch_labels else "base"
        )
        await asyncio.to_thread(upgrade, empty_database_url, revision.revision)
        here = await _sync(empty_database_url, _catalog)
        await asyncio.to_thread(downgrade, empty_database_url, down)
        assert await _sync(empty_database_url, _catalog) == below, revision.revision
        await asyncio.to_thread(upgrade, empty_database_url, revision.revision)
        assert await _sync(empty_database_url, _catalog) == here, revision.revision
        below = here


async def test_models_match_the_migrations(empty_database_url: str) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    assert await _sync(empty_database_url, _drift) == []
    await asyncio.to_thread(downgrade, empty_database_url)
    await asyncio.to_thread(upgrade, empty_database_url)
    assert await _sync(empty_database_url, _drift) == []  # and after a second upgrade


def test_branches_are_labelled() -> None:
    script = ScriptDirectory.from_config(config())
    kernel_dir = (KERNEL / "migrations").resolve()
    module_by_dir = {(path / "migrations").resolve(): path.name for path in module_dirs()}
    for revision in script.walk_revisions():
        if revision.down_revision is not None:
            continue
        folder = Path(revision.path).resolve().parent
        if folder == kernel_dir:
            assert revision.branch_labels == {"kernel"}, revision.path
        else:
            module_id = module_by_dir[folder]
            assert revision.branch_labels == {module_id}, revision.path
            assert revision.dependencies, f"{revision.path} must depend on the kernel"


# --- the snapshot sees what a bad downgrade or seed would change (audit F18) ---

MUTANTS = {
    "an index dropped": "DROP INDEX ix_auth_session_user_id",
    "a unique constraint dropped": "ALTER TABLE auth_api_key DROP CONSTRAINT uq_auth_api_key_key_id",
    "a check constraint dropped": "ALTER TABLE auth_api_key DROP CONSTRAINT ck_auth_api_key_mode_known",
    "a server default dropped": "ALTER TABLE auth_user ALTER COLUMN status DROP DEFAULT",
    "a column made nullable": "ALTER TABLE auth_session ALTER COLUMN epoch DROP NOT NULL",
    "a column's type widened": "ALTER TABLE auth_role ALTER COLUMN name TYPE text",
    "a seeded role deleted": "DELETE FROM auth_role WHERE id = 'editor'",
    "a seeded grant deleted": "DELETE FROM auth_role_permission WHERE role_id = 'admin'",
    "a leftover type": "CREATE TYPE leftover AS ENUM ('a')",
    "a leftover sequence": "CREATE SEQUENCE leftover_seq",
    "a leftover function": "CREATE FUNCTION leftover() RETURNS int LANGUAGE sql AS 'SELECT 1'",
}


@pytest.mark.parametrize("change", MUTANTS.values(), ids=MUTANTS.keys())
async def test_the_snapshot_sees_each_change(empty_database_url: str, change: str) -> None:
    await asyncio.to_thread(upgrade, empty_database_url)
    before = await _sync(empty_database_url, _catalog)

    def mutate(connection: Connection) -> None:
        connection.execute(text(change))
        connection.commit()

    await _sync(empty_database_url, mutate)
    assert await _sync(empty_database_url, _catalog) != before
