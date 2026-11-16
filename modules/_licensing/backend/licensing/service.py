"""All of licensing's logic; routers call these with a session and typed arguments.

Slow work goes to kernel jobs. Holds export_user_data(user_id) and delete_user_data(user_id) (SPEC 10).
"""

# TODO, one function per route:
# - list_works: The beat store, filterable by BPM, key, genre and mood.
# - check_license: Public license check: work, tier, buyer name and date, nothing private.
# - save_work: Create or update a work and its files.
# - save_tiers: The tier table: formats, prices, terms, exclusive flag.
