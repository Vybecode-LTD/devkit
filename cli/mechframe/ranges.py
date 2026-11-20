"""Semver ranges, as a manifest's `requires` writes them (SPEC.md sections 5 and 12).

A range is one or more comparators separated by spaces, all of which must hold:

| Written | Means |
| --- | --- |
| `^1.2.3`, `^1.2`, `^1` | the same first non-zero part: `>=1.2.3 <2.0.0` (`^0.1` is `>=0.1.0 <0.2.0`) |
| `~1.2.3`, `~1.2`, `~1` | the same minor: `>=1.2.3 <1.3.0` (`~1` is `>=1.0.0 <2.0.0`) |
| `1.2.3`, `=1.2.3` | that version |
| `>=1.2.3`, `>1.2.3`, `<=1.2.3`, `<1.2.3` | as written; a missing minor or patch is 0 |
| `*` | any |

A pre-release meets a range as its precedence says, from the lowest pre-release
of each lower bound: MechFrame's kernel is `0.1.0-dev.0` until it's released,
and a module that requires `^0.1` takes it (decision 0050).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from mechframe.versions import Version, parse

_PARTIAL = re.compile(r"^(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?(?:\.(0|[1-9]\d*))?$")
_COMPARATOR = re.compile(r"^(\^|~|>=|<=|>|<|=)?(.+)$")
#: The lowest pre-release of a version: `1.2.3-0` comes before every other `1.2.3-…`.
_FLOOR = (0,)


class RangeError(ValueError):
    """Not a range this CLI reads."""


def _floor(major: int, minor: int, patch: int) -> Version:
    return Version(major, minor, patch, _FLOOR)


def _partial(text: str, written: str) -> tuple[int, int | None, int | None]:
    found = _PARTIAL.match(text)
    if found is None:
        raise RangeError(f"{written!r} isn't a semver range (such as ^0.1 or >=1.2.0 <2.0.0).")
    major, minor, patch = found.groups()
    return int(major), None if minor is None else int(minor), None if patch is None else int(patch)


Test = Callable[[Version], bool]


def _comparator(part: str, written: str) -> list[Test]:
    found = _COMPARATOR.match(part)
    if found is None:  # `.+` matches any part but an empty one
        raise RangeError(f"{written!r} isn't a semver range (such as ^0.1 or >=1.2.0 <2.0.0).")
    operator, rest = found.groups()
    if operator in (None, "=") and rest != "*":
        try:
            exact = parse(rest)
        except ValueError:
            exact = None
        if exact is not None:
            return [lambda version: version == exact]
    if rest == "*" and operator is None:
        return []
    major, minor, patch = _partial(rest, written)
    low = (major, minor or 0, patch or 0)
    if operator == "^":
        if major > 0 or minor is None:
            high = (major + 1, 0, 0)
        elif minor > 0 or patch is None:
            high = (0, minor + 1, 0)
        else:
            high = (0, 0, (patch or 0) + 1)
        return [lambda v: v >= _floor(*low), lambda v: v < _floor(*high)]
    if operator == "~":
        high = (major + 1, 0, 0) if minor is None else (major, minor + 1, 0)
        return [lambda v: v >= _floor(*low), lambda v: v < _floor(*high)]
    if operator in (None, "="):
        # A partial version: every version it names, `1.2` as `>=1.2.0 <1.3.0`.
        high = (major + 1, 0, 0) if minor is None else (major, minor + 1, 0)
        return [lambda v: v >= _floor(*low), lambda v: v < _floor(*high)]
    bound = _floor(*low)
    if operator == ">=":
        return [lambda v: v >= bound]
    if operator == "<":
        return [lambda v: v < bound]
    release = Version(*low)
    if operator == ">":
        return [lambda v: v > release]
    return [lambda v: v <= release]  # "<="


def tests(written: str) -> list[Test]:
    """The checks `written` makes, all of which must hold. Raises RangeError."""
    parts = written.split()
    if not parts or "||" in parts:
        raise RangeError(f"{written!r} isn't a semver range (such as ^0.1 or >=1.2.0 <2.0.0).")
    found: list[Test] = []
    for part in parts:
        found += _comparator(part, written)
    return found


def satisfies(version: str, written: str) -> bool:
    """Whether `version` meets the range `written`. Raises RangeError on a range
    it can't read, and ValueError on a version semver refuses."""
    checked = parse(version)
    return all(test(checked) for test in tests(written))
