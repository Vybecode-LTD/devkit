"""All of comments's logic; routers call these with a session and typed arguments.

Slow work goes to kernel jobs. Holds export_user_data(user_id) and delete_user_data(user_id) (SPEC 10).
"""

# TODO, one function per route:
# - get_thread: Approved comments, two levels deep, sorted by top or newest.
# - post_comment: Members and (if allowed) guests; first comments and guest comments wait for approval. Rate limited.
# - approval_queue: Comments waiting for approval, oldest first.
# - approve: Approve one comment; emits comments.comment.approved.
