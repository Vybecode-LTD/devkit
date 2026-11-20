"""A module's settings in a site's `.env.example` and `.railway/railway.ts`
(SPEC.md section 12, step 4; decisions 0048 and 0050).

`.env.example` gets a block of the module's own at its end, after the line
`ENV_MARK`, each setting blank, with its description:

    # fixture-notes, added by mechframe add
    # The feed the notes come from (required)
    FIXTURE_NOTES_FEED_URL=

`remove` comments the block's settings out and says so in its first line; a
later `add` writes it again. `.railway/railway.ts` gets each setting as
`preserve()`, under a `// <id>` line after `RAILWAY_MARK`, since an apply
deletes a variable on the service that the file doesn't list (decision 0048).
`remove` leaves those lines, so an apply keeps what the owner typed into
Railway.

Every text here has LF line endings: the caller keeps the file's own.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

ENV = ".env.example"
RAILWAY = ".railway/railway.ts"
ENV_MARK = "# --- The modules' settings, appended by mechframe add ---"
RAILWAY_MARK = "// --- The modules' settings, added by mechframe add ---"

_ACTIVE = re.compile(r"^([A-Z][A-Z0-9_]*)=")
_LISTED = re.compile(r"^\s*([A-Z][A-Z0-9_]*):")
_CLOSE = re.compile(r"^\s*},\s*$")


class SettingsError(Exception):
    """The site's file isn't as the template wrote it; the message says what's missing."""


def _added(module_id: str) -> str:
    return f"# {module_id}, added by mechframe add"


def _removed(module_id: str) -> str:
    return f"# {module_id}, removed by mechframe remove: its settings commented out"


def _span(lines: list[str], module_id: str) -> tuple[int, int] | None:
    """Where the module's block is: its first line, and the line after its last."""
    heads = {_added(module_id), _removed(module_id)}
    for start, line in enumerate(lines):
        if line in heads:
            end = start + 1
            while end < len(lines) and lines[end].strip():
                end += 1
            return start, end
    return None


def active(text: str, outside: str | None = None) -> set[str]:
    """Every setting `text` sets, but those in the block of the module `outside`."""
    lines = text.split("\n")
    span = _span(lines, outside) if outside else None
    found = set()
    for number, line in enumerate(lines):
        if span and span[0] <= number < span[1]:
            continue
        matched = _ACTIVE.match(line)
        if matched:
            found.add(matched.group(1))
    return found


def _one_line(text: str) -> str:
    return " ".join(text.split())


def env_with(text: str, module_id: str, env: Iterable[Mapping[str, Any]]) -> str:
    """`.env.example` with the module's block: written at the end, or in place
    of the one a `remove` left. A module with no settings has no block."""
    block = [_added(module_id)]
    for setting in env:
        note = _one_line(str(setting["description"]))
        block += [f"# {note}{' (required)' if setting['required'] else ''}", f"{setting['name']}="]
    lines = text.split("\n")
    span = _span(lines, module_id)
    if span is not None:
        lines[span[0] : span[1]] = block if len(block) > 1 else []
        return "\n".join(lines)
    if len(block) == 1:
        return text
    if ENV_MARK not in lines:
        raise SettingsError(f"{ENV} has no line {ENV_MARK!r} to add a module's settings after.")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join([*lines, "", *block, ""])


def env_without(text: str, module_id: str) -> str:
    """`.env.example` with the module's settings commented out."""
    lines = text.split("\n")
    span = _span(lines, module_id)
    if span is None:
        return text
    start, end = span
    lines[start] = _removed(module_id)
    for number in range(start + 1, end):
        if _ACTIVE.match(lines[number]):
            lines[number] = f"# {lines[number]}"
    return "\n".join(lines)


def _env_block(lines: list[str]) -> tuple[int, int]:
    """The marker's line in `railway.ts`, and the line that closes `env`."""
    marks = [number for number, line in enumerate(lines) if line.strip() == RAILWAY_MARK]
    if len(marks) != 1:
        raise SettingsError(
            f"{RAILWAY} has no line {RAILWAY_MARK!r} to add a module's settings after."
        )
    for number in range(marks[0] + 1, len(lines)):
        if _CLOSE.match(lines[number]):
            return marks[0], number
    raise SettingsError(f"{RAILWAY}: nothing closes `env` after {RAILWAY_MARK!r}.")


def listed(script: str) -> set[str]:
    """Every variable `railway.ts` names."""
    return {found.group(1) for found in map(_LISTED.match, script.split("\n")) if found}


def railway_with(script: str, module_id: str, names: Iterable[str]) -> str:
    """`railway.ts` with each of `names` it doesn't name yet, as `preserve()`,
    in the module's group."""
    lines = script.split("\n")
    mark, close = _env_block(lines)
    known = listed(script)
    missing = [name for name in names if name not in known]
    if not missing:
        return script
    indent = lines[mark][: len(lines[mark]) - len(lines[mark].lstrip())]
    entries = [f"{indent}{name}: preserve()," for name in missing]
    head = f"{indent}// {module_id}"
    groups = [number for number in range(mark + 1, close) if lines[number] == head]
    if groups:
        at = groups[0] + 1
        while at < close and not lines[at].lstrip().startswith("//"):
            at += 1
        lines[at:at] = entries
    else:
        lines[close:close] = [head, *entries]
    return "\n".join(lines)
