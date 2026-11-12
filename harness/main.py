"""The harness's app: the kernel and every module in this repo.

    python -m uvicorn harness.main:app --reload

With DEBUG=true in .env, the API docs are at http://localhost:8000/docs.
Run `python -m harness.migrations upgrade` first.
"""

from __future__ import annotations

from harness.registry import discover
from kernel import create_app

app = create_app(modules=discover())
