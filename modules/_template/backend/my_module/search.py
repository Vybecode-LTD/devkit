"""my-module: what site search finds of it (kernel.search, decision 0052).

Each kind of content the public may find gets a source here, and module.json's
`content_types` names the same type with `"search": true`. The start refuses
either one without the other. For example:

    class Items(search.Source):
        content_type = "my-module.item"

        async def document(self, db, content_id):
            item = await db.scalar(
                select(Item).where(Item.id == content_id, lifecycle.visible(Item))
            )
            return None if item is None else search.Document(
                "my-module.item", item.id, item.title, item.text, f"/my-module/{item.slug}"
            )

        async def documents(self, db):
            for item in await db.scalars(select(Item).where(lifecycle.visible(Item))):
                yield search.Document(...)

    SEARCH = (Items(),)

`document` answers None for what isn't public. The kernel indexes content
with lifecycle as it's published and unpublished; content without it, and an
edit of what's published, calls `search.index(db, doc)` or
`search.remove(db, type, id)` in the same transaction. The body is plain
text. A module that nothing searches deletes this file.
"""

from __future__ import annotations

from kernel import search

SEARCH: tuple[search.Source, ...] = ()
