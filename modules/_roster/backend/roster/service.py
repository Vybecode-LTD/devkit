"""All of roster's logic; routers call these with a session and typed arguments.

Slow work goes to kernel jobs. Holds export_user_data(user_id) and delete_user_data(user_id) (SPEC 10).
"""

# TODO, one function per route:
# - list_profiles: Visible profiles in ring order.
# - get_profile: One profile; the page gathers work from other modules through their public surfaces.
# - save_profile: Staff with the permission, or the member who owns the profile (require_owner_or).
