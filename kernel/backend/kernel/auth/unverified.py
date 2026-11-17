"""Unverified accounts are removed after 7 days (SPEC.md 14.7; decision 0035;
contract dev plans/contracts/k3-jobs.md).

`kernel.remove_unverified` runs hourly. It removes an account only when its
address isn't verified (`email_verified_at` is empty) and was set more than 7
days ago (`email_set_at`), it is `active`, and it holds no role but `member`: an owner's or
staff account is never removed, however it was made, and neither is a
suspended one or one on its way out (`deleting`, which has its own grace period).

**One lock order:** each batch locks the account rows first, as every route
does (`accounts.lock`), skipping any a request holds: a verification that
holds its account while the sweep runs wins, and the sweep takes the
account next hour if it's still unverified. The delete checks the same
conditions again, so nothing that changed since the select is removed. The
account's sessions, tokens, factors and roles go with it by cascade; the
audit log keeps one row each, under the account's id alone, and every module
listening hears `auth.user.deleted` for it (kernel.events), emitted in the
same transaction as the delete.

**The clock restarts with the address** (the owner's choice): an email
change's undo puts back the address the account had, unverified if it was
(decision 0024), and sets `email_set_at`, so the address put back gets a full
7 days to be verified however old the account is. An account someone made
with another person's address is still removed a week after the undo that
gave the address back.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, delete, select

from kernel import clock, events, jobs
from kernel.auth import audit
from kernel.auth.models import User, UserRole

AGE = timedelta(days=7)
BATCH = 100
ACTION = "auth.user.removed_unverified"


def _removable(cutoff: datetime) -> list[ColumnElement[bool]]:
    holds_more = (
        select(UserRole.user_id)
        .where(UserRole.user_id == User.id, UserRole.role_id != "member")
        .exists()
    )
    return [
        User.email_verified_at.is_(None),
        User.email_set_at < cutoff,
        User.status == "active",
        ~holds_more,
    ]


async def _remove(ctx: jobs.Context) -> None:
    cutoff = clock.now() - AGE
    while True:
        async with ctx.sessions() as db:
            found = (
                select(User.id)
                .where(*_removable(cutoff))
                .order_by(User.created_at)
                .limit(BATCH)
                .with_for_update(skip_locked=True)
            )
            ids = list((await db.scalars(found)).all())
            if not ids:
                await db.rollback()
                return
            removed = (
                await db.scalars(
                    delete(User).where(User.id.in_(ids), *_removable(cutoff)).returning(User.id)
                )
            ).all()
            for user_id in removed:
                audit.record_by_kernel(db, ACTION, "success", subject=user_id)
                await events.emit(db, "auth.user.deleted", events.UserDeleted(user_id=user_id))
            await db.commit()
        if len(ids) < BATCH:
            return


REMOVE = jobs.scheduled("17 * * * *", "kernel.remove_unverified", timeout=900)(_remove)
