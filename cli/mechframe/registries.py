"""The two registries a site's app is built from (SPEC.md section 12, step 3).

`backend/app/modules.py` lists the modules' ids for the backend, and
`web/src/modules.ts` imports each one's web binding (`module.web.ts`) for
`mountApp`. Both are written whole from the lock's modules, in id order, as
the harness finds its own, so they can't drift from it. A module with no web
binding has no line in `modules.ts`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

PYTHON = "backend/app/modules.py"
WEB = "web/src/modules.ts"
#: Black's and the site's ESLint line length.
WIDTH = 100

_PYTHON_HEAD = '''"""The modules this site has, by id. Written by `mechframe add` and `mechframe remove`.

Don't edit by hand: they keep it matched to mechframe.lock.json's modules.
"""

from __future__ import annotations

'''
_WEB_HEAD = """// The modules' web bindings this site has. Written by `mechframe add` and
// `mechframe remove`: don't edit by hand.
import type { ModuleDefinition } from "@/kernel";
"""


def identifier(module_id: str) -> str:
    """The name `modules.ts` imports a module's binding as: `media-gallery` is
    `mediaGalleryModule`, which no id can make a reserved word."""
    first, *rest = module_id.split("-")
    return first + "".join(part.capitalize() for part in rest) + "Module"


def python(module_ids: Iterable[str]) -> str:
    ids = sorted(module_ids)
    one_line = "MODULE_IDS: tuple[str, ...] = ("
    if not ids:
        return _PYTHON_HEAD + one_line + ")\n"
    items = ", ".join(f'"{each}"' for each in ids)
    if len(ids) == 1:
        items += ","
    if len(one_line) + len(items) + 1 <= WIDTH:
        return _PYTHON_HEAD + one_line + items + ")\n"
    lines = "".join(f'    "{each}",\n' for each in ids)
    return _PYTHON_HEAD + one_line + "\n" + lines + ")\n"


def web(bound: Iterable[str]) -> str:
    """`bound`: the ids of the modules that have a web binding."""
    ids = sorted(bound)
    imports = "".join(
        f'import {identifier(each)} from "./modules/{each}/module.web";\n' for each in ids
    )
    names = ", ".join(identifier(each) for each in ids)
    start = "export const modules: ModuleDefinition[] = ["
    if len(start) + len(names) + 2 <= WIDTH:
        body = f"{start}{names}];\n"
    else:
        body = start + "\n" + "".join(f"  {identifier(each)},\n" for each in ids) + "];\n"
    return _WEB_HEAD + imports + "\n" + body


def newline(path: Path) -> str:
    """The file's own line ending, so a checkout's CRLF stays CRLF."""
    try:
        return "\r\n" if b"\r\n" in path.read_bytes() else "\n"
    except FileNotFoundError:
        return "\n"


def encoded(text: str, ending: str) -> bytes:
    return text.replace("\n", ending).encode("utf-8")
