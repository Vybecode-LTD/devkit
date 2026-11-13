"""The DevKit kernel: the always-installed core every module depends on.

This file is the kernel's public surface (SPEC.md section 6). Modules and
sites import from `kernel` only; every other name in this package is private
and may change in any release. The surface follows semver with `__version__`.

Built so far (K1): the database, settings, module switches, crypto, errors,
rate limits, access marks and the app factory. From K2: the access
dependencies (`current_user`, `optional_user`, `require_permission`,
`require_owner_or`, `require_recent_auth`). Email, storage, events, jobs,
notifications, moderation and audit arrive in K3.
"""

from kernel import crypto
from kernel.access import public
from kernel.app import create_app
from kernel.auth.dependencies import (
    OwnerOr,
    current_user,
    optional_user,
    require_owner_or,
    require_permission,
    require_recent_auth,
)
from kernel.db import Base, Database, for_saving, get_db, one_row_only
from kernel.errors import Problem
from kernel.modules import InstalledModule, Manifest, require_module
from kernel.ratelimit import rate_limit
from kernel.settings import settings
from kernel.version import __version__

__all__ = [
    "Base",
    "Database",
    "InstalledModule",
    "Manifest",
    "OwnerOr",
    "Problem",
    "__version__",
    "create_app",
    "crypto",
    "current_user",
    "for_saving",
    "get_db",
    "one_row_only",
    "optional_user",
    "public",
    "rate_limit",
    "require_module",
    "require_owner_or",
    "require_permission",
    "require_recent_auth",
    "settings",
]
