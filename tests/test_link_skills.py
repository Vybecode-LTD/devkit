"""tools/link_skills links each skill once and never replaces anything."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools import link_skills


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("alpha", "beta"):
        (tmp_path / "skills" / name).mkdir(parents=True)
        (tmp_path / "skills" / name / "SKILL.md").write_text(f"# {name}\n", "utf-8")
    (tmp_path / "skills" / "notes").mkdir()  # no SKILL.md: not a skill
    monkeypatch.setattr(link_skills, "SOURCES", tmp_path / "skills")
    monkeypatch.setattr(link_skills, "TARGET", tmp_path / ".claude" / "skills")
    return tmp_path


@pytest.mark.skipif(os.name == "nt", reason="symlinks; Windows makes junctions")
def test_links_each_skill_and_runs_again(repo: Path) -> None:
    assert link_skills.main() == 0
    linked = repo / ".claude" / "skills"
    assert sorted(path.name for path in linked.iterdir()) == ["alpha", "beta"]
    assert (linked / "alpha" / "SKILL.md").read_text("utf-8") == "# alpha\n"
    assert link_skills.main() == 0


def test_never_replaces_something_else(repo: Path) -> None:
    (repo / ".claude" / "skills" / "alpha").mkdir(parents=True)
    assert link_skills.main() == 1
    assert not (repo / ".claude" / "skills" / "alpha" / "SKILL.md").exists()
