"""Event payloads portfolio emits and its handlers (SPEC 11). Payloads hold ids and a version `v`; handlers run twice safely.

Emits: portfolio.piece.published, portfolio.piece.deleted. Listens: auth.user.deleted.
"""
