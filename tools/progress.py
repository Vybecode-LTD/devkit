"""The framework's progress, from one file: `docs/progress.json`.

    python -m tools.progress           # rewrite docs/PROGRESS.md and the ledger's rows
    python -m tools.progress --check   # exit 1 if either is stale or the data is wrong

`docs/progress.json` lists every phase to MechFrame v1.0 and after it, each with
its steps and their status. Edit only that file. This tool makes both views of
it from the same data:

- `docs/PROGRESS.md`, the document in the repo;
- `dev plans/progress-ledger/rows.json`, the same steps as flat rows, which the
  visual ledger (`ledger_url` in the JSON) is published from.

`tests/test_progress.py` fails when either file is stale, or when the data
names a status, a milestone or a decision record that doesn't exist. It checks
the files in the repo, not the published ledger: that matches only once the new
rows are uploaded to it (`dev plans/progress-ledger/README.md`). Progress counts
steps, not effort: each step is one row, whatever its size.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "progress.json"
DOC = ROOT / "docs" / "PROGRESS.md"
ROWS = ROOT / "dev plans" / "progress-ledger" / "rows.json"
DECISIONS = ROOT / "docs" / "decisions"
REPO = "https://github.com/mechframe/mechframe"

#: Each status, in the order the views list them, with its label.
STATUSES = {
    "done": "Done",
    "review": "In review",
    "next": "Next",
    "todo": "To do",
    "waiting": "Waiting",
    "later": "Later",
}
_ITEM_KEYS = {"name", "status", "prs", "decisions", "note"}
_PHASE_KEYS = {"id", "milestone", "name", "goal", "gate", "gate_passed", "items"}


def load(path: Path | None = None) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((path or DATA).read_text(encoding="utf-8"))
    return data


def _decision_files() -> dict[str, str]:
    return {path.name[:4]: path.name for path in DECISIONS.glob("[0-9][0-9][0-9][0-9]-*.md")}


def problems(data: dict[str, Any], decisions: dict[str, str] | None = None) -> list[str]:
    """What's wrong with the data, one line each; empty when it's sound."""
    decisions = _decision_files() if decisions is None else decisions
    found: list[str] = []
    milestones = [milestone.get("id") for milestone in data.get("milestones", [])]
    if not milestones:
        found.append("No milestones.")
    found += [
        f"Milestone {milestone!r} appears twice."
        for milestone in sorted({m for m in milestones if milestones.count(m) > 1}, key=str)
    ]
    seen: set[str] = set()
    for phase in data.get("phases", []):
        where = f"Phase {phase.get('id')!r}"
        found += [
            f"{where} has an unknown key {key!r}." for key in sorted(set(phase) - _PHASE_KEYS)
        ]
        if phase.get("id") in seen:
            found.append(f"{where} appears twice.")
        seen.add(phase.get("id"))
        if phase.get("milestone") not in milestones:
            found.append(f"{where} names milestone {phase.get('milestone')!r}, which isn't listed.")
        if "gate" in phase and not isinstance(phase.get("gate_passed"), bool):
            found.append(f"{where} has a gate but no gate_passed true or false.")
        if not phase.get("items"):
            found.append(f"{where} has no steps.")
        for item in phase.get("items", []):
            step = f"{where}, step {item.get('name')!r}"
            found += [
                f"{step} has an unknown key {key!r}." for key in sorted(set(item) - _ITEM_KEYS)
            ]
            if item.get("status") not in STATUSES:
                found.append(
                    f"{step} has status {item.get('status')!r}; use one of {', '.join(STATUSES)}."
                )
            if not all(isinstance(pr, int) and pr > 0 for pr in item.get("prs", [])):
                found.append(f"{step} lists a PR that isn't a number.")
            found += [
                f"{step} names decision {decision!r}, which has no record in docs/decisions."
                for decision in item.get("decisions", [])
                if decision not in decisions
            ]
    return found


def _count(items: list[dict[str, Any]]) -> Counter[str]:
    return Counter(item["status"] for item in items)


def _bar(done: int, total: int) -> str:
    percent = done * 100 // total if total else 0
    filled = percent // 10
    return f"{'█' * filled}{'░' * (10 - filled)} {percent}% ({done} of {total})"


def _prs(item: dict[str, Any]) -> str:
    return ", ".join(f"[#{pr}]({REPO}/pull/{pr})" for pr in item.get("prs", []))


def _decisions(item: dict[str, Any], decisions: dict[str, str]) -> str:
    return ", ".join(f"[{d}](decisions/{decisions[d]})" for d in item.get("decisions", []))


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render(data: dict[str, Any], decisions: dict[str, str] | None = None) -> str:
    """docs/PROGRESS.md for `data`."""
    decisions = _decision_files() if decisions is None else decisions
    phases = data["phases"]
    lines = [
        "# MechFrame progress",
        "",
        "Generated from `docs/progress.json` by `python -m tools.progress`: edit the JSON, then run "
        "the tool. `tests/test_progress.py` fails when this page is stale. The same data feeds the "
        f"[visual progress ledger]({data['ledger_url']}).",
        "",
        f"Updated {data['updated']}, `main` at `{data['main']}`. Progress counts steps, not effort: "
        "each row below is one step, whatever its size.",
        "",
        "## Overall",
        "",
        "| Milestone | " + " | ".join(STATUSES.values()) + " | Progress |",
        "| --- | " + " | ".join("---:" for _ in STATUSES) + " | --- |",
    ]
    groups = [
        (m["name"], [p for p in phases if p["milestone"] == m["id"]]) for m in data["milestones"]
    ]
    for name, members in [*groups, ("Everything", phases)]:
        items = [item for phase in members for item in phase["items"]]
        counts = _count(items)
        cells = " | ".join(str(counts[status]) for status in STATUSES)
        lines.append(f"| {name} | {cells} | {_bar(counts['done'], len(items))} |")
    for milestone in data["milestones"]:
        lines += ["", f"## {milestone['name']}", "", milestone["goal"]]
        for phase in [p for p in phases if p["milestone"] == milestone["id"]]:
            items = phase["items"]
            done = _count(items)["done"]
            gate = ""
            if "gate" in phase:
                gate = " · gate passed" if phase["gate_passed"] else " · gate not passed yet"
            lines += [
                "",
                f"### {phase['name']} · {done} of {len(items)} done{gate}",
                "",
                phase["goal"],
            ]
            if "gate" in phase:
                lines += ["", f"Gate: {phase['gate']}"]
            plain = all(
                not (item.get("prs") or item.get("decisions") or item.get("note")) for item in items
            )
            statuses = {item["status"] for item in items}
            if plain and len(statuses) == 1:
                names = ", ".join(f"`{item['name']}`" for item in items)
                lines += ["", f"{STATUSES[statuses.pop()]}: {names}."]
                continue
            lines += [
                "",
                "| Step | Status | PRs | Decisions | Note |",
                "| --- | --- | --- | --- | --- |",
            ]
            for item in items:
                lines.append(
                    f"| {_cell(item['name'])} | {STATUSES[item['status']]} | {_prs(item)} | "
                    f"{_decisions(item, decisions)} | {_cell(item.get('note', ''))} |"
                )
    return "\n".join(lines) + "\n"


def rows(data: dict[str, Any], code: str) -> dict[str, Any]:
    """The ledger's file: every step as one row, and where the rows came from."""
    names = {milestone["id"]: milestone["name"] for milestone in data["milestones"]}
    out = []
    for phase_order, phase in enumerate(data["phases"], start=1):
        gate = "" if "gate" not in phase else ("passed" if phase["gate_passed"] else "not passed")
        for step_order, item in enumerate(phase["items"], start=1):
            out.append(
                {
                    "milestone": names[phase["milestone"]],
                    "phase_order": phase_order,
                    "phase_id": phase["id"],
                    "phase": phase["name"],
                    "gate": gate,
                    "step_order": step_order,
                    "step": item["name"],
                    "status": item["status"],
                    "status_label": STATUSES[item["status"]],
                    "prs": " ".join(f"#{pr}" for pr in item.get("prs", [])),
                    "decisions": " ".join(item.get("decisions", [])),
                    "note": item.get("note", ""),
                }
            )
    meta = [
        {"label": "tools/progress.py", "value": code, "type": "code", "lang": "python"},
        {"label": "Input", "value": "docs/progress.json"},
        {"label": "Updated", "value": data["updated"]},
        {"label": "main", "value": data["main"]},
    ]
    return {"rows": out, "meta": meta}


def outputs(data: dict[str, Any]) -> dict[Path, str]:
    code = Path(__file__).read_text(encoding="utf-8")
    return {
        DOC: render(data),
        ROWS: json.dumps(rows(data, code), indent=1, ensure_ascii=False) + "\n",
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    data = load()
    wrong = problems(data)
    if wrong:
        print("\n".join(wrong))
        return 1
    stale = []
    for path, text in outputs(data).items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if "--check" in args:
            stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"Wrote {path.relative_to(ROOT).as_posix()}")
    if stale:
        print(f"Stale: {', '.join(stale)}. Run python -m tools.progress.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
