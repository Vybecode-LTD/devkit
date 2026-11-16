"""All of portfolio's logic; routers call these with a session and typed arguments.

Slow work goes to kernel jobs. Holds export_user_data(user_id) and delete_user_data(user_id) (SPEC 10).
"""

# TODO, one function per route:
# - list_pieces: Published pieces, filterable by discipline.
# - get_piece: One piece with its images.
# - save_piece: Create or update a piece; sends `version`.
