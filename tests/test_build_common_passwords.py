"""The common-password list's build is reproducible (NOTICE, audit F41)."""

from __future__ import annotations

from pathlib import Path

from tools import build_common_passwords as tool


def test_the_same_sources_give_the_same_bytes_under_any_name(tmp_path: Path) -> None:
    source = tmp_path / "list.txt"
    source.write_text("short\ncorrect horse battery\nCorrect Horse Battery\n" + "x" * 300 + "\n")
    first, second = tmp_path / "a.txt.gz", tmp_path / "elsewhere" / "b.gz"
    second.parent.mkdir()
    assert tool.main([str(first), str(source)]) == 0
    assert tool.main([str(second), str(source)]) == 0
    assert first.read_bytes() == second.read_bytes()


def test_only_whole_lengths_are_kept_casefolded_once() -> None:
    assert tool.keep("Correct Horse Battery\r\n") == "correct horse battery"
    assert tool.keep("short") is None
    assert tool.keep("x" * 257) is None
    assert tool.keep("broken � password") is None
