"""SQLAlchemy models (SPEC.md section 10).

Tables are named my_module_<name>, use UUID keys and timestamptz in UTC, and may
reference only this module's tables and auth_user. Every model subclasses the
kernel's `Base`, so the site's migrations see it:

    from kernel import Base
"""
