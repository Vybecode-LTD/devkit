# kernel (Python package)

Planned subpackages, one per service (SPEC.md section 6): `auth`, `users`, `roles`, `settings`, `db`, `email`, `notifications`, `storage`, `events`, `jobs`, `moderation`, `audit`, `security`, `crypto`, `ratelimit`, `modules`, `errors`.

`__init__.py` re-exports the public API: `get_db`, `current_user`, `optional_user`, `require_permission`, `require_recent_auth`, `require_module`, `settings`, `email`, `notify`, `storage`, `events`, `jobs`, `moderation`, `audit`, `rate_limit`, `crypto`, `Problem`, `ai`. Nothing else is public.
