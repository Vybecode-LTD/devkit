"""This site's app: the kernel, its modules and its own pages.

    python -m uvicorn app.main:app --reload     (with PYTHONPATH=backend)

Run `python -m app.migrations upgrade` first. With DEBUG=true in .env the API
docs are at http://localhost:8000/docs.
"""

from __future__ import annotations

from app import installed
from app.modules import MODULE_IDS
from app.site.pages import SITE_PAGES
from kernel import create_app
from kernel.config import KernelConfig

app = create_app(modules=installed(MODULE_IDS), config=KernelConfig(), site=SITE_PAGES)
