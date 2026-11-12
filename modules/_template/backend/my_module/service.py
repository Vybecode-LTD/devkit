"""All of the module's logic. Routers call this; it takes a session and typed arguments.

Slow work (over about a second) goes to kernel jobs, never into a request.

If any table references a user, this file also holds export_user_data(user_id) and
delete_user_data(user_id), which the kernel calls for account export and deletion
(SPEC.md section 10).
"""
