"""HTTP routes (SPEC.md section 7).

The kernel mounts this router at /api/my-module and puts require_module("my-module")
in front of it. Every route declares its access: public, member (current_user) or a
permission (require_permission). Nothing changes state on GET. Errors are kernel
Problem responses with a stable code such as "my-module.item_not_found".
"""

from fastapi import APIRouter

router = APIRouter()
