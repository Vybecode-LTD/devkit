"""The hash a lock file records for each copied file (K5 contract §2)."""

from __future__ import annotations

import hashlib
from pathlib import Path


def digest(path: Path) -> str:
    """`sha256:` of the file's bytes with `\\r\\n` read as `\\n`, so the line
    endings Git writes in a Windows checkout don't count as an edit."""
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return "sha256:" + hashlib.sha256(data).hexdigest()
