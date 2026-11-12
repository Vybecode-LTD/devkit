"""The DevKit kernel: the always-installed core every module depends on.

This file is the kernel's public surface (SPEC.md section 6). Modules import
from `kernel` only; every other name in this package is private and may change
in any release. The public surface follows semver with `__version__`.
"""

__version__ = "0.0.0"

__all__ = ["__version__"]
