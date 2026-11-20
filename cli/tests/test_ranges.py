"""The semver ranges a manifest's `requires` writes (`mechframe.ranges`, decision 0050)."""

from __future__ import annotations

import pytest

from mechframe.ranges import RangeError, satisfies


@pytest.mark.parametrize(
    ("version", "written", "meets"),
    [
        ("0.1.0", "^0.1", True),
        ("0.1.9", "^0.1", True),
        ("0.2.0", "^0.1", False),
        ("0.0.9", "^0.1", False),
        ("0.1.0-dev.0", "^0.1", True),  # MechFrame's kernel until it's released
        ("0.2.0-dev.0", "^0.1", False),
        ("1.4.2", "^1.2", True),
        ("2.0.0", "^1.2", False),
        ("2.0.0-rc.1", "^1.2", False),
        ("0.0.3", "^0.0.3", True),
        ("0.0.4", "^0.0.3", False),
        ("1.2.9", "~1.2", True),
        ("1.3.0", "~1.2", False),
        ("1.9.0", "~1", True),
        ("1.2.3", "1.2.3", True),
        ("1.2.4", "1.2.3", False),
        ("1.2.3", "=1.2.3", True),
        ("1.2.7", "1.2", True),
        ("1.3.0", "1.2", False),
        ("1.2.0", ">=1.2.0 <2.0.0", True),
        ("2.0.0", ">=1.2.0 <2.0.0", False),
        ("1.2.0", ">1.2.0", False),
        ("1.2.1", ">1.2.0", True),
        ("1.2.0", "<=1.2.0", True),
        ("1.2.1", "<=1.2.0", False),
        ("9.9.9", "*", True),
    ],
)
def test_a_range_holds_what_it_says(version: str, written: str, meets: bool) -> None:
    assert satisfies(version, written) is meets


@pytest.mark.parametrize(
    "written", ["", "0.x", "^", "^a.b", "1.2.3 || 2.0.0", "v1.2.3", ">=01.2.0"]
)
def test_a_range_it_cant_read_is_refused(written: str) -> None:
    with pytest.raises(RangeError):
        satisfies("1.2.3", written)


def test_a_version_semver_refuses_is_refused() -> None:
    with pytest.raises(ValueError, match="isn't a semver version"):
        satisfies("1.2", "^1.2")
