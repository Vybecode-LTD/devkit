"""fixture-notes' listener, for the tests: it hears every new account, so a
site's test can see a delivery queued (decision 0051, Codex on #95)."""

from kernel import events, jobs


@events.on("auth.user.created", "fixture-notes.greet_account")
async def greet_account(ctx: jobs.Context, event: events.Event) -> None:
    """Does nothing: the job queued for it is what's checked."""
