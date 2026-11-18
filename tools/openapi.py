"""The committed OpenAPI documents (K4, decision 0042; SPEC.md 4 and 18).

    python -m tools.openapi           # rewrite kernel/openapi.json and modules/<id>/openapi.json
    python -m tools.openapi --check   # exit 1 if one is stale, missing or left over

The app is built as the harness builds it, with every module in the repo
(`harness.registry`), and its document (`kernel.openapi.document`) is cut by
owner: the kernel's paths into `kernel/openapi.json`, each module's into its
own folder. The files are made, never edited by hand. The web kernel's types
come from the kernel's (`npm run api:types`), and `tests/test_openapi.py`
fails when a file is stale.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts

import harness  # noqa: F401  (importing it puts the kernel's backend on sys.path)

ROOT = Path(__file__).resolve().parent.parent
KERNEL_FILE = "kernel/openapi.json"
TITLE = "MechFrame kernel"


def build_app() -> FastAPI:
    """The harness's app with every module, on made-up secrets: nothing in a
    document depends on them, and nothing connects to a database."""
    from harness.registry import discover
    from kernel import create_app
    from kernel.config import KernelConfig

    config = KernelConfig(
        debug=True,
        secret_key=secrets.token_urlsafe(48),
        encryption_keys=Fernet.generate_key().decode(),
        site_url="https://mechframe.test",
        modules="*",
        web_dist="",
        jobs_in_web=False,
    )
    return create_app(modules=discover(), config=config)


def api_routes(app: FastAPI) -> list[tuple[str, APIRoute]]:
    """Every API route but the harness's test support, with its full path."""
    found: list[tuple[str, APIRoute]] = []
    for context in iter_route_contexts(app.routes):
        route = getattr(context, "route", context)
        if not isinstance(route, APIRoute):
            continue
        path = getattr(context, "path", None) or route.path
        if path.startswith("/api/") and not path.startswith("/api/_test"):
            found.append((path, route))
    return found


def specs() -> dict[str, dict[str, Any]]:
    """Every committed document, by its path from the repo's root."""
    from harness.registry import discover
    from kernel import __version__
    from kernel.openapi import by_owner, document

    titles = {"kernel": (TITLE, __version__)}
    for module in discover():
        titles[module.id] = (
            str(module.manifest.raw.get("name", module.id)),
            str(module.manifest.raw.get("version", "0.0.0")),
        )
    made = by_owner(document(build_app()), titles)
    return {
        (KERNEL_FILE if owner == "kernel" else f"modules/{owner}/openapi.json"): spec
        for owner, spec in made.items()
    }


def references(spec: Any) -> list[str]:
    """Every `$ref` in a document."""
    from kernel.openapi import references as walk

    return list(walk(spec))


def main(argv: list[str] | None = None, *, root: Path = ROOT) -> int:
    from kernel.openapi import dumped

    args = sys.argv[1:] if argv is None else argv
    check = "--check" in args
    wanted = {name: dumped(spec) for name, spec in specs().items()}
    wrong: list[str] = []
    for name, text in sorted(wanted.items()):
        path = root / name
        # Bytes, not text: a file in another encoding is stale, never a traceback
        # (CodeRabbit on #78); .gitattributes keeps these files LF.
        if path.exists() and path.read_bytes() == text.encode("utf-8"):
            continue
        if check:
            wrong.append(f"stale or missing: {name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"Wrote {name}")
    for path in sorted((root / "modules").glob("*/openapi.json")):
        name = path.relative_to(root).as_posix()
        if name in wanted:
            continue
        if check:
            wrong.append(f"no installed module answers it: {name}")
        else:
            path.unlink()
            print(f"Removed {name}")
    if wrong:
        print("\n".join(wrong) + "\nRun python -m tools.openapi, then npm run api:types.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
