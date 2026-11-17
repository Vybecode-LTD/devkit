"""my-module: the event payloads it owns, and its listeners (kernel.events,
SPEC.md section 11, decision 0036).

Every payload here is declared with `@events.payload` and listed in
module.json's `events.emits`; every listener is found by its type and its
event listed in `events.listens`. Payloads hold ids, not rows. For example:

    import uuid

    @events.payload("my-module.thing.published", v=1)
    class ThingPublished(events.Payload):
        thing_id: uuid.UUID

and, in the module's service, in the same transaction as the change:

    await events.emit(db, "my-module.thing.published", ThingPublished(thing_id=thing.id))

A listener is a job of this module, named `my-module.<name>`, tried up to 8
times. It runs at least once: make it safe to run twice. Every try sees the
same `event.id`. Another module's payload is read into a model of this
module's own, holding the fields it needs (modules don't import each other).
"""

from kernel import events, jobs


@events.on("auth.user.deleted", "my-module.forget_user")
async def forget_user(ctx: jobs.Context, event: events.Event) -> None:
    """Erases what this module holds on a person whose account is gone: a
    delete by their id, which changes nothing the second time."""
    user_id = event.parse(events.UserDeleted).user_id  # noqa: F841  (the line below uses it)
    async with ctx.sessions() as db:
        # await db.execute(delete(MyThing).where(MyThing.owner_id == user_id))
        await db.commit()
