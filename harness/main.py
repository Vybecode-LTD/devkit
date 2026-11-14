"""The harness's app: the kernel and every module in this repo.

    python -m uvicorn harness.main:app --reload

With DEBUG=true in .env, the API docs are at http://localhost:8000/docs.
Run `python -m harness.migrations upgrade` first. Sign-up is open here, as
the contract suite expects of the harness (docs/contracts/auth-api.md).
"""

from __future__ import annotations

from harness.registry import discover
from kernel import create_app
from kernel.config import KernelConfig

app = create_app(modules=discover(), config=KernelConfig(sign_up_mode="open"))
