"""Semver versions, ordered by precedence (semver.org 2.0.0, item 11)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering

_IDENTIFIER = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    rf"(?:-({_IDENTIFIER}(?:\.{_IDENTIFIER})*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    pre: tuple[int | str, ...] = ()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        mine, theirs = (self.major, self.minor, self.patch), (other.major, other.minor, other.patch)
        if mine != theirs:
            return mine < theirs
        if not self.pre or not other.pre:
            return bool(self.pre) and not other.pre  # a pre-release comes before its release
        for left, right in zip(self.pre, other.pre, strict=False):
            if left == right:
                continue
            if isinstance(left, int) and isinstance(right, int):
                return left < right
            if isinstance(left, int) or isinstance(right, int):
                return isinstance(left, int)  # numbers come before words
            return left < right
        return len(self.pre) < len(other.pre)

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        return f"{text}-{'.'.join(str(part) for part in self.pre)}" if self.pre else text


def parse(text: str) -> Version:
    found = _SEMVER.match(text)
    if found is None:
        raise ValueError(f"{text!r} isn't a semver version (major.minor.patch).")
    major, minor, patch, pre = found.groups()
    parts: tuple[int | str, ...] = ()
    if pre:
        parts = tuple(int(part) if part.isdigit() else part for part in pre.split("."))
    return Version(int(major), int(minor), int(patch), parts)
