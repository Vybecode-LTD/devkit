"""my-module: its publishable content (kernel.lifecycle, decision 0052).

Content that's drafted, scheduled and published subclasses
`lifecycle.Publishable`, names its type, `my-module.<entity>`, and is listed
here; module.json's `content_types` names the same type with
`"lifecycle": true`. The start refuses either one without the other. For
example:

    class Item(lifecycle.Publishable, Base):
        __tablename__ = "my_module_item"
        __content_type__ = "my-module.item"
        ...

    PUBLISHABLE = (Item,)

Its migration writes `*lifecycle.columns()` and
`*lifecycle.table_args("my_module_item")`; public reads filter with
`lifecycle.visible(Item)`; `lifecycle.publish`, `schedule` and `unpublish`
change its state and emit `kernel.content.published` and
`kernel.content.unpublished`. A module with nothing to publish deletes this
file.
"""

from __future__ import annotations

PUBLISHABLE: tuple[type, ...] = ()
