"""Event payloads roster emits and its handlers (SPEC 11). Payloads hold ids and a version `v`; handlers run twice safely.

Emits: roster.profile.published, roster.profile.deleted. Listens: auth.user.deleted.
"""
