"""my-module: what people may report, and how it's hidden or deleted
(kernel.moderation, decision 0039).

Each kind is a class of `moderation.Kind` declared with `@moderation.kind`,
named `my-module.<entity>`, and listed on the module's
`InstalledModule(reportable=...)`. `describe` says what the thing is now (None
when there's no such thing, an id that can't be one included); `apply` hides or
deletes it, in the caller's transaction, for each action the kind lists; and
`dismissed`, when staff find nothing wrong, shows again what the filters held
(by default it does nothing). A kind may list neither: a
profile is reported so staff can time out or ban the person, not to hide it.
For example:

    @moderation.kind("my-module.comment", actions=("hide", "delete"))
    class Comment(moderation.Kind):
        async def describe(self, db, id):
            # A report can name any id: ASCII digits only, so "²", " 12" and
            # "1_0" (which int() reads as 10) are no such thing.
            if not (id.isascii() and id.isdigit()):
                return None
            found = await db.get(models.Comment, int(id))
            if found is None:
                return None
            return moderation.Item(found.author_id, found.body, f"/talk/{found.post_id}#c{id}")

        async def apply(self, db, id, action):
            ...  # hide: mark it hidden; delete: remove it

        async def dismissed(self, db, id):
            ...  # show it again if the filters held it

Before showing new text to others, screen it, and hold what the filters hold:

    verdict = await moderation.screen(db, body)
    if verdict.hold:
        comment.hidden = True  # the poster sees the same answer either way
        await moderation.hold(db, ("my-module.comment", comment.id), reasons=verdict.reasons)

Every route that posts takes `Depends(moderation.can_post)` instead of
`current_user`, so a timed-out member can't post.
"""

from kernel import moderation  # noqa: F401  (the examples above use it)
