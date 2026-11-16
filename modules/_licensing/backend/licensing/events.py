"""Event payloads licensing emits and its handlers (SPEC 11). Payloads hold ids and a version `v`; handlers run twice safely.

Emits: licensing.license.issued, licensing.work.sold_exclusive. Listens: payments.checkout.completed, auth.user.deleted.
"""
