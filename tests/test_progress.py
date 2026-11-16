"""The progress document and the ledger's rows match docs/progress.json, and
the data names only statuses, milestones and decisions that exist."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tools import progress


def test_the_data_is_sound() -> None:
    assert progress.problems(progress.load()) == []


def test_the_document_and_the_rows_are_current() -> None:
    # Fails after an edit to docs/progress.json until `python -m tools.progress` runs.
    for path, text in progress.outputs(progress.load()).items():
        assert (
            path.read_text(encoding="utf-8") == text
        ), f"{path.name} is stale: run python -m tools.progress"
    assert progress.main(["--check"]) == 0


SMALL: dict[str, Any] = {
    "updated": "2026-01-02",
    "main": "abc1234",
    "ledger_url": "https://example.test/ledger",
    "milestones": [{"id": "v1", "name": "One", "goal": "The first."}],
    "phases": [
        {
            "id": "a",
            "milestone": "v1",
            "name": "Phase A",
            "goal": "Do A.",
            "gate": "A passes.",
            "gate_passed": False,
            "items": [
                {
                    "name": "Built | piped",
                    "status": "done",
                    "prs": [5],
                    "decisions": ["0001"],
                    "note": "n",
                },
                {"name": "Waiting step", "status": "waiting"},
            ],
        },
        {
            "id": "b",
            "milestone": "v1",
            "name": "Phase B",
            "goal": "Do B.",
            "items": [{"name": "x", "status": "todo"}],
        },
    ],
}
DECISIONS = {"0001": "0001-stack.md"}


def test_the_document_counts_links_and_lists() -> None:
    text = progress.render(SMALL, DECISIONS)
    assert "| One | 1 | 0 | 0 | 1 | 1 | 0 | ███░░░░░░░ 33% (1 of 3) |" in text
    assert "### Phase A · 1 of 2 done · gate not passed yet" in text
    assert (
        "| Built \\| piped | Done | [#5](https://github.com/Vybecode-LTD/devkit/pull/5) | [0001](decisions/0001-stack.md) | n |"
        in text
    )
    assert "### Phase B · 0 of 1 done\n\nDo B.\n\nTo do: `x`." in text
    assert "[visual progress ledger](https://example.test/ledger)" in text


def test_the_rows_are_one_per_step_with_their_source() -> None:
    made = progress.rows(SMALL, "print('code')")
    assert [row["step"] for row in made["rows"]] == ["Built | piped", "Waiting step", "x"]
    first = made["rows"][0]
    assert first["status_label"] == "Done"
    assert first["prs"] == "#5"
    assert first["gate"] == "not passed"
    assert made["rows"][2]["gate"] == ""
    assert made["meta"][0] == {
        "label": "tools/progress.py",
        "value": "print('code')",
        "type": "code",
        "lang": "python",
    }
    json.dumps(made)


def _broken(change: Any) -> list[str]:
    data = copy.deepcopy(SMALL)
    change(data)
    return progress.problems(data, DECISIONS)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (lambda d: d["phases"][0]["items"][0].update(status="finished"), "status 'finished'"),
        (lambda d: d["phases"][0]["items"][0].update(prs=["58"]), "isn't a number"),
        (lambda d: d["phases"][0]["items"][0].update(decisions=["0999"]), "decision '0999'"),
        (lambda d: d["phases"][0]["items"][0].update(owner="me"), "unknown key 'owner'"),
        (lambda d: d["phases"][1].update(milestone="v9"), "milestone 'v9'"),
        (lambda d: d["phases"][1].update(id="a"), "appears twice"),
        (lambda d: d["phases"][0].pop("gate_passed"), "no gate_passed"),
        (lambda d: d["phases"][1].update(items=[]), "has no steps"),
        (lambda d: d["phases"][1].update(colour="red"), "unknown key 'colour'"),
        (lambda d: d.update(milestones=[]), "No milestones"),
        (
            lambda d: d["milestones"].append({"id": "v1", "name": "Again", "goal": "Same id."}),
            "Milestone 'v1' appears twice",
        ),
    ],
)
def test_bad_data_is_named(change: Any, problem: str) -> None:
    assert any(problem in found for found in _broken(change))


def test_main_writes_then_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "progress.json"
    source.write_text(json.dumps(SMALL), encoding="utf-8")
    monkeypatch.setattr(progress, "DATA", source)
    monkeypatch.setattr(progress, "DOC", tmp_path / "PROGRESS.md")
    monkeypatch.setattr(progress, "ROWS", tmp_path / "ledger" / "rows.json")
    monkeypatch.setattr(progress, "ROOT", tmp_path)
    monkeypatch.setattr(progress, "_decision_files", lambda: DECISIONS)
    assert progress.main(["--check"]) == 1
    assert "Stale: PROGRESS.md, ledger/rows.json" in capsys.readouterr().out
    assert progress.main([]) == 0
    assert progress.main(["--check"]) == 0
    broken = copy.deepcopy(SMALL)
    broken["phases"][0]["items"][0]["status"] = "finished"
    source.write_text(json.dumps(broken), encoding="utf-8")
    assert progress.main([]) == 1
    assert "status 'finished'" in capsys.readouterr().out
