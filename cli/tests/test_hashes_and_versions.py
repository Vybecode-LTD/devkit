"""A copied file's hash ignores line endings; versions order by semver."""

from __future__ import annotations

from pathlib import Path

import pytest

from mechframe import hashes, versions


def test_a_file_s_hash_ignores_the_line_endings_git_writes(tmp_path: Path) -> None:
    lf = tmp_path / "lf.py"
    crlf = tmp_path / "crlf.py"
    lf.write_bytes(b"one\ntwo\n")
    crlf.write_bytes(b"one\r\ntwo\r\n")
    assert hashes.digest(lf) == hashes.digest(crlf)
    assert hashes.digest(lf).startswith("sha256:")
    assert len(hashes.digest(lf)) == len("sha256:") + 64


def test_a_change_to_a_file_changes_its_hash(tmp_path: Path) -> None:
    one = tmp_path / "one.py"
    one.write_bytes(b"one\n")
    before = hashes.digest(one)
    one.write_bytes(b"one!\n")
    assert hashes.digest(one) != before


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("0.1.0", "0.1.1"),
        ("0.1.9", "0.1.10"),
        ("0.9.0", "1.0.0"),
        ("0.1.0-dev.0", "0.1.0"),
        ("0.1.0-dev.1", "0.1.0-dev.2"),
        ("0.1.0-dev.9", "0.1.0-dev.10"),
        ("0.1.0-alpha", "0.1.0-beta"),
        ("0.1.0-1", "0.1.0-alpha"),
    ],
)
def test_versions_order_by_semver(lower: str, higher: str) -> None:
    assert versions.parse(lower) < versions.parse(higher)
    assert not versions.parse(higher) < versions.parse(lower)


def test_equal_versions_are_equal() -> None:
    assert versions.parse("0.1.0-dev.0") == versions.parse("0.1.0-dev.0")


@pytest.mark.parametrize("bad", ["", "1", "1.2", "v1.2.3", "01.2.3", "1.2.3-"])
def test_a_version_that_isn_t_semver_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="semver"):
        versions.parse(bad)
