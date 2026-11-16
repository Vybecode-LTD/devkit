"""Event payloads comments emits and its handlers (SPEC 11). Payloads hold ids and a version `v`; handlers run twice safely.

Emits: comments.comment.created, comments.comment.approved. Listens: auth.user.deleted.
"""
