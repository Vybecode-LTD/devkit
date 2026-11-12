"""The dev harness: a small app that mounts the kernel and every module in this
repo, for tests and local runs (KICKOFF.md, K0). K5 turns it into the site
template.

Importing it puts the kernel's backend and each module's on `sys.path`, the
way a site's `backend/` folder holds them side by side.
"""

from __future__ import annotations

import sys

from harness.layout import backend_dirs

for _path in reversed(backend_dirs()):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
