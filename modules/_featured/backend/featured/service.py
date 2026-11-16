"""All of featured's logic; routers call these with a session and typed arguments.

Slow work goes to kernel jobs.
"""

# TODO, one function per route:
# - live_slot: The slot's live placements, in order (starts_at <= now < ends_at, or no dates).
# - list_slots: Every slot with its placement count and what's live now.
# - get_slot: All placements in a slot, live, scheduled and ended, with the slot's version.
# - replace_slot: Replace the ordered list in one save. Checks `version` (SaveConflict) and each item against `accepts`; emits featured.placement.changed; audited.
# - oembed: Title and thumbnail for a pasted YouTube link, through the kernel's SSRF guard.
