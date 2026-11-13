"""Each module's settings: typed, versioned, merged on save (SPEC.md section 7).

Lifted from VybeSite's conditional saves (`services/settings_versions.py`,
`models/version.py`), for any module. A module declares a Pydantic model whose
every field has a default; a field typed `SecretStr` (or `SecretStr | None`)
is a secret, sealed at rest (`kernel.crypto`) and never shown or kept in a
version. A secret anywhere else (in a list, a nested model, a union with
another type, or as `SecretBytes`) can't be sealed field by field, so
`register` refuses the model.

    class BlogSettings(BaseModel):
        posts_per_page: int = 10
        api_key: SecretStr | None = None

    cfg = await settings.for_module(db, "blog")       # a BlogSettings

**Versions.** Every save that changes something records the next version,
numbered from 1; version 0 is the defaults. A version holds the form as the
admin saw it after the save, a secret only as `{"kept": bool, "changes": n}`,
and which fields changed, who saved it, when and how (`via`).

**Saves are conditional.** A save says which version its form was read at.
Two admins can open one form, and the second save no longer silently undoes
the first. Under the module's advisory lock, a save from an older version is
merged field by field with what was saved since:

- a field only this save changed is this save's;
- a field only others changed keeps their value (reported as `merged`);
- a field both changed to different values is a **conflict**: 409
  (`kernel.settings_conflict`) with both values, who and when, saving nothing.

A secret is a change only when typed: `None` keeps it, `""` removes it (back
to its default), any other text or `SecretStr` replaces it. Both saves typing
one is a conflict.

Values are kept as JSON and read back in JSON mode, so a strict model works:
a date or an enum arrives as its JSON text from a form and as itself from
code, and both read the same. Values are compared as the model reads them:
a stale form sending `"10"` for an int that was 10, or a datetime at
midnight for a date, hasn't changed it.
A save that changes nothing ends its transaction (when it commits), so the
lock goes with it.

VybeSite also merges list fields item by item; here a list is one value.
"""

from __future__ import annotations

import json
import types
import typing
import uuid
import zlib
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel, SecretBytes, SecretStr, ValidationError
from pydantic_core import PydanticSerializationError, to_jsonable_python
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import crypto
from kernel.errors import Problem
from kernel.models import Setting, SettingVersion

#: The first key of every settings advisory lock: pg_advisory_xact_lock(LOCK_CLASS, module).
LOCK_CLASS = 84712031

Model = TypeVar("Model", bound=BaseModel)


_UNIONS = (typing.Union, types.UnionType)


def _is_secret(annotation: Any) -> bool:
    """`SecretStr`, or `SecretStr | None`: the shapes a field's secret takes."""
    if annotation is SecretStr:
        return True
    args = typing.get_args(annotation)
    return (
        typing.get_origin(annotation) in _UNIONS
        and SecretStr in args
        and all(arg in (SecretStr, type(None)) for arg in args)
    )


def _types_in(annotation: Any, seen: set[type] | None = None) -> Iterator[Any]:
    """Every type an annotation can hold, through unions, containers and
    nested models."""
    seen = set() if seen is None else seen
    yield annotation
    for arg in typing.get_args(annotation):
        yield from _types_in(arg, seen)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return
        seen.add(annotation)
        for info in annotation.model_fields.values():
            yield from _types_in(info.annotation, seen)


def _unsealable(model: type[BaseModel]) -> list[str]:
    """The fields holding a secret somewhere other than as a field's own value."""
    return [
        name
        for name, info in model.model_fields.items()
        if not _is_secret(info.annotation)
        and any(kind in (SecretStr, SecretBytes) for kind in _types_in(info.annotation))
    ]


def secret_fields(model: type[BaseModel]) -> frozenset[str]:
    return frozenset(
        name for name, info in model.model_fields.items() if _is_secret(info.annotation)
    )


@dataclass
class Saved:
    """A save's outcome: the version the settings now stand at, the fields
    this save changed and the fields it kept from others' saves."""

    version: int
    changed: list[str]
    merged: list[str] = field(default_factory=list)


class SettingsRegistry:
    """The settings models of the modules installed, by module id."""

    def __init__(self) -> None:
        self.models: dict[str, type[BaseModel]] = {}

    def register(self, module_id: str, model: type[BaseModel]) -> None:
        try:
            model()
        except ValidationError as error:
            raise ValueError(
                f"{module_id}'s settings model needs a default for every field."
            ) from error
        unsealable = _unsealable(model)
        if unsealable:
            raise ValueError(
                f"{module_id}'s settings keep a secret only as a SecretStr field of its own "
                f"(SecretStr or SecretStr | None); {', '.join(unsealable)} would be saved "
                "unsealed or as its mask."
            )
        self.models[module_id] = model

    def model(self, module_id: str) -> type[BaseModel]:
        try:
            return self.models[module_id]
        except KeyError:
            raise Problem("kernel.settings_unknown", 404, f"{module_id} has no settings.") from None

    # --- reading ------------------------------------------------------------

    async def _row(self, db: AsyncSession, module_id: str, *, lock: bool = False) -> Setting | None:
        statement = select(Setting).where(Setting.module_id == module_id)
        if lock:
            statement = statement.with_for_update()
        statement = statement.execution_options(populate_existing=True)
        return (await db.execute(statement)).scalars().first()

    def _model_from(self, model: type[Model], stored: Mapping[str, Any]) -> Model:
        secrets = secret_fields(model)
        values: dict[str, Any] = {}
        for name in model.model_fields:
            if name not in stored:
                continue
            if name in secrets:
                sealed = (stored[name] or {}).get("sealed")
                if sealed:
                    values[name] = crypto.open(sealed)
                # Removed: the field's default.
            else:
                values[name] = stored[name]
        # JSON mode: what's stored is JSON, and a strict model reads its text forms.
        return model.model_validate_json(json.dumps(values))

    async def for_module(self, db: AsyncSession, module_id: str) -> BaseModel:
        """The module's settings as its model, secrets opened."""
        model = self.model(module_id)
        row = await self._row(db, module_id)
        return self._model_from(model, row.values if row else {})

    def _masked(self, model: type[BaseModel], stored: Mapping[str, Any]) -> dict[str, Any]:
        """The form as an admin sees it: values, and each secret as whether
        one is kept and how many times it has changed."""
        defaults = model().model_dump(mode="json")
        secrets = secret_fields(model)
        form: dict[str, Any] = {}
        for name in model.model_fields:
            if name in secrets:
                entry = stored.get(name) or {}
                form[name] = {"kept": bool(entry.get("sealed")), "changes": entry.get("changes", 0)}
            else:
                form[name] = stored.get(name, defaults[name])
        return form

    async def form(self, db: AsyncSession, module_id: str) -> dict[str, Any]:
        """`{"version": n, "values": {...}}`, secrets masked: what an admin form reads."""
        model = self.model(module_id)
        row = await self._row(db, module_id)
        return {
            "version": row.version if row else 0,
            "values": self._masked(model, row.values if row else {}),
        }

    async def history(self, db: AsyncSession, module_id: str) -> list[dict[str, Any]]:
        """Every saved version, newest first, without its values."""
        self.model(module_id)
        statement = (
            select(SettingVersion)
            .where(SettingVersion.module_id == module_id)
            .order_by(SettingVersion.number.desc())
        )
        return [
            {
                "number": version.number,
                "changed": version.changed,
                "via": version.via,
                "saved_at": version.saved_at,
                "saved_by_id": version.saved_by_id,
            }
            for version in (await db.execute(statement)).scalars()
        ]

    # --- saving -------------------------------------------------------------

    async def _lock(self, db: AsyncSession, module_id: str) -> None:
        key = zlib.crc32(module_id.encode("utf-8")) - 2**31
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:kind, :key)"), {"kind": LOCK_CLASS, "key": key}
        )

    async def _version(
        self, db: AsyncSession, module_id: str, number: int
    ) -> SettingVersion | None:
        statement = select(SettingVersion).where(
            SettingVersion.module_id == module_id, SettingVersion.number == number
        )
        return (await db.execute(statement)).scalars().first()

    async def save(
        self,
        db: AsyncSession,
        module_id: str,
        changes: Mapping[str, Any],
        *,
        version: int,
        by: uuid.UUID | None = None,
        via: str = "form",
        commit: bool = True,
    ) -> Saved:
        """Save `changes`, a form's values by field, read at `version`.
        Raises Problem: 422 for an unknown field, a version not yet saved or
        values the model refuses; 409 for a conflict. Nothing is written then."""
        model = self.model(module_id)
        secrets = secret_fields(model)
        unknown = sorted(set(changes) - set(model.model_fields))
        if unknown:
            raise Problem(
                "kernel.invalid_request",
                422,
                f"{module_id}'s settings have no {', '.join(unknown)}.",
                errors={name: ["Not a setting."] for name in unknown},
            )

        await self._lock(db, module_id)
        row = await self._row(db, module_id, lock=True)
        current = row.version if row else 0
        stored: dict[str, Any] = dict(row.values) if row else {}
        if version > current:
            raise Problem(
                "kernel.settings_version_unknown",
                422,
                f"These settings have no version {version} yet. Reload the page and save again.",
            )

        now = self._masked(model, stored)
        typed = {name for name in secrets if changes.get(name) is not None}
        yours = self._as_read(
            model,
            stored,
            self._as_json(module_id, {n: v for n, v in changes.items() if n not in secrets}),
        )

        merged: list[str] = []
        if version < current:
            older = await self._version(db, module_id, version)
            base = older.values if older else self._masked(model, {})
            conflicts, kept = self._merge(model, base, now, yours, typed, changes)
            if conflicts:
                newest = await self._version(db, module_id, current)
                raise Problem(
                    "kernel.settings_conflict",
                    409,
                    "Someone else saved these settings since you opened them, and changed "
                    f"{', '.join(c['field'] for c in conflicts)} too. Reload to see their "
                    "values, then make your change again.",
                    extra={
                        "version": current,
                        "conflicts": conflicts,
                        "by": str(newest.saved_by_id) if newest and newest.saved_by_id else None,
                        "at": newest.saved_at.isoformat() if newest else None,
                    },
                )
            for name in kept:
                yours.pop(name, None)
            merged = sorted(kept)

        # The new stored values: what's there, with this save's on top.
        new_stored = dict(stored)
        for name, value in yours.items():
            new_stored[name] = value
        for name in typed:
            entry = dict(stored.get(name) or {})
            value = changes[name]
            text_value = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
            entry["sealed"] = crypto.seal(text_value) if text_value else None
            entry["changes"] = int(entry.get("changes", 0)) + 1
            new_stored[name] = entry

        # The model checks every value, secrets opened.
        try:
            checked = self._model_from(model, new_stored)
        except ValidationError as error:
            errors: dict[str, list[str]] = {}
            for item in error.errors():
                errors.setdefault(".".join(str(p) for p in item["loc"]), []).append(item["msg"])
            raise Problem(
                "kernel.invalid_request", 422, "Some of these settings aren't valid.", errors=errors
            ) from None
        dumped = checked.model_dump(mode="json")
        for name in model.model_fields:
            if name not in secrets and name in new_stored:
                new_stored[name] = dumped[name]

        after = self._masked(model, new_stored)
        changed = sorted(name for name in after if after[name] != now[name])
        if not changed:
            if commit:
                await db.commit()  # ends the transaction, and the lock with it
            return Saved(version=current, changed=[], merged=merged)

        if row is None:
            row = Setting(module_id=module_id, values=new_stored, version=current + 1)
            db.add(row)
        else:
            row.values = new_stored
            row.version = current + 1
        row.updated_by_id = by
        db.add(
            SettingVersion(
                module_id=module_id,
                number=current + 1,
                values=after,
                changed=changed,
                via=via,
                saved_by_id=by,
            )
        )
        if commit:
            await db.commit()
        else:
            await db.flush()
        # K3: emit kernel.settings.changed and audit it.
        return Saved(version=current + 1, changed=changed, merged=merged)

    @staticmethod
    def _as_json(module_id: str, sent: Mapping[str, Any]) -> dict[str, Any]:
        """Values from code (a date, an enum, a UUID) as the JSON a form would
        send. Raises Problem 422 for one with no JSON form."""
        out: dict[str, Any] = {}
        errors: dict[str, list[str]] = {}
        for name, value in sent.items():
            try:
                out[name] = to_jsonable_python(value)
            except PydanticSerializationError:
                errors[name] = ["Not a value these settings can hold."]
        if errors:
            raise Problem(
                "kernel.invalid_request",
                422,
                f"Some of {module_id}'s settings aren't valid.",
                errors=errors,
            )
        return out

    def _as_read(
        self, model: type[BaseModel], stored: Mapping[str, Any], sent: dict[str, Any]
    ) -> dict[str, Any]:
        """The sent values as the model reads and stores them (JSON mode), so
        the merge compares like with like. Values the model refuses are left
        as sent: the check after the merge reports them."""
        if not sent:
            return sent
        try:
            read = self._model_from(model, {**stored, **sent}).model_dump(mode="json")
        except ValidationError:
            return sent
        return {name: read[name] for name in sent}

    @staticmethod
    def _merge(
        model: type[BaseModel],
        base: Mapping[str, Any],
        now: Mapping[str, Any],
        yours: Mapping[str, Any],
        typed: set[str],
        changes: Mapping[str, Any],
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """Conflicts, and the fields whose value others set and this save
        didn't change (kept as others left them)."""
        conflicts: list[dict[str, Any]] = []
        kept: set[str] = set()
        defaults = model().model_dump(mode="json")
        for name, value in yours.items():
            then = base.get(name, defaults[name])
            if value == now[name]:
                continue
            if now[name] == then:
                continue  # only this save changed it
            if value == then:
                kept.add(name)  # only others changed it
                continue
            conflicts.append({"field": name, "yours": value, "theirs": now[name]})
        for name in typed:
            then = (base.get(name) or {}).get("changes", 0)
            if now[name]["changes"] != then:
                conflicts.append({"field": name, "secret": True})
        return conflicts, kept


#: The site's settings: `create_app` registers each module's model here.
settings = SettingsRegistry()

__all__ = ["LOCK_CLASS", "Saved", "SettingsRegistry", "secret_fields", "settings"]
