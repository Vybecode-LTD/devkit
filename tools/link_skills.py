"""Links each project skill in `skills/` into `.claude/skills/`, so Claude Code
loads it (KICKOFF.md K0 step 2).

    python -m tools.link_skills

On Windows each link is a directory junction, which needs no admin rights; on
other systems a symlink. `skills/` holds the sources and is committed;
`.claude/skills/` is gitignored. Safe to run again: a link already in place is
left alone, and anything else at that name is reported, never replaced.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "skills"
TARGET = ROOT / ".claude" / "skills"


def _same(link: Path, source: Path) -> bool:
    try:
        return link.resolve() == source.resolve()
    except OSError:
        return False


def _link(link: Path, source: Path) -> None:
    if os.name == "nt":
        # mklink /J makes a junction: a directory link any user may create.
        subprocess.run(  # noqa: S603  (fixed command, our own paths)
            ["cmd", "/c", "mklink", "/J", str(link), str(source)],  # noqa: S607
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(source, target_is_directory=True)


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    problems = 0
    for source in sorted(path for path in SOURCES.iterdir() if (path / "SKILL.md").is_file()):
        link = TARGET / source.name
        if link.exists() or link.is_symlink():
            if _same(link, source):
                print(f"ok      {source.name}")
            else:
                print(f"skipped {source.name}: something else is already at {link}")
                problems += 1
            continue
        _link(link, source)
        print(f"linked  {source.name}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
