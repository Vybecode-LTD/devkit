"""The modules in this repo, as the harness's app is built from them.

A site lists its modules in `backend/app/modules.py`, written by
`devkit add` (SPEC.md section 12). The harness finds them instead, by the
fixed layout (SPEC.md section 4):

- `backend/<id_>/router.py`'s `router`, mounted at /api/<id>;
- `backend/<id_>/schemas.py`'s `Settings`, the module's settings model;
- `backend/<id_>/__init__.py`'s `CSP`, the hosts it adds while it's on, as
  (directive, https origin) pairs;
- `backend/<id_>/emails.py`'s `EMAILS`, its email templates (kernel.email);
- `backend/<id_>/jobs.py`'s jobs: every `kernel.jobs.Job` in it, which
  `@jobs.handler` and `@jobs.scheduled` make (decision 0035);
- `backend/<id_>/events.py`'s event payloads (the classes it declares with
  `@events.payload`) and its listeners (every `kernel.events.Listener`,
  which `@events.on` makes; decision 0036);
- `backend/<id_>/moderation.py`'s kinds: every class it declares with
  `@moderation.kind` (decision 0039);
- `backend/<id_>/server_copy.py`'s `PAGES`, its public pages
  (kernel.server_copy, decision 0041).
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any

import harness  # noqa: F401  (puts the kernel and modules on sys.path)
from harness.layout import module_dirs
from kernel.events import Listener, Payload, declaration
from kernel.jobs import Job
from kernel.moderation import Kind
from kernel.modules import InstalledModule, Manifest


def _attribute(module_name: str, attribute: str) -> Any:
    if importlib.util.find_spec(module_name) is None:
        return None
    return getattr(importlib.import_module(module_name), attribute, None)


def _jobs(module_name: str) -> tuple[Job, ...]:
    if importlib.util.find_spec(module_name) is None:
        return ()
    found = vars(importlib.import_module(module_name)).values()
    return tuple(value for value in found if isinstance(value, Job))


def module_events(
    module_name: str,
) -> tuple[tuple[type[Payload], ...], tuple[Listener, ...]]:
    """The payloads `module_name` declares itself (not ones it imports, such
    as the kernel's) and its listeners."""
    if importlib.util.find_spec(module_name) is None:
        return (), ()
    module = importlib.import_module(module_name)
    found = list(vars(module).values())
    payloads = tuple(
        value
        for value in found
        if isinstance(value, type)
        and value.__module__ == module.__name__
        and declaration(value) is not None
    )
    listeners = tuple(value for value in found if isinstance(value, Listener))
    return payloads, listeners


def module_kinds(module_name: str) -> tuple[type[Kind], ...]:
    """The kinds `module_name` declares itself: not `Kind`, nor one it imports."""
    if importlib.util.find_spec(module_name) is None:
        return ()
    module = importlib.import_module(module_name)
    return tuple(
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, Kind)
        and value.__module__ == module.__name__
        and value.name
    )


def discover() -> list[InstalledModule]:
    found = []
    for folder in module_dirs():
        manifest = Manifest.from_file(folder / "module.json")
        package = manifest.package
        if importlib.util.find_spec(package) is None:
            found.append(InstalledModule(manifest))
            continue
        payloads, listeners = module_events(f"{package}.events")
        found.append(
            InstalledModule(
                manifest,
                router=_attribute(f"{package}.router", "router"),
                settings=_attribute(f"{package}.schemas", "Settings"),
                csp=tuple(_attribute(package, "CSP") or ()),
                emails=dict(_attribute(f"{package}.emails", "EMAILS") or {}),
                jobs=_jobs(f"{package}.jobs"),
                payloads=payloads,
                listeners=listeners,
                reportable=module_kinds(f"{package}.moderation"),
                pages=_attribute(f"{package}.server_copy", "PAGES"),
            )
        )
    return found
