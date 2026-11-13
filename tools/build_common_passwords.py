r"""Builds the bundled common-password list (SPEC.md 14.2).

    python -m tools.build_common_passwords OUT.txt.gz SOURCE.txt [SOURCE.txt ...] \
        [--brand-check C:\DEV\VybeSite\vybesite\scripts\brand_check.py]

Each source is a plain list, one password a line, most common first. The
output keeps only what the length rule wouldn't already refuse (12 to 256
characters after NFC), casefolded, each once, in the order first seen, so
the most common come first. Lines that are encoding damage (the replacement
character, or the mojibake `пїѕ` a UTF-8/CP1251 mix-up leaves) or that hold
control characters are dropped. The gzip header holds no time and a fixed
name, so the same sources in the same order give the same bytes.

The bundled list, rebuilt exactly (the sources, their licences and the
commit are in NOTICE):

1. From SecLists at commit dbfb830d95e4f3da4fb7d7d277ed597de0ed7a18,
   Passwords/Common-Credentials/: 100k-most-used-passwords-NCSC.txt, then
   xato-net-10-million-passwords-1000000.txt, then Pwdb_top-1000000.txt.
2. Django 6.1.3's django/contrib/auth/common-passwords.txt.gz, taken from
   the wheel and un-gzipped to django-common-passwords.txt, last.
3. Run, from the repo root:

       python -m tools.build_common_passwords \
           kernel/backend/kernel/auth/data/common-passwords.txt.gz \
           100k-most-used-passwords-NCSC.txt \
           xato-net-10-million-passwords-1000000.txt \
           Pwdb_top-1000000.txt django-common-passwords.txt \
           --brand-check C:\DEV\VybeSite\vybesite\scripts\brand_check.py

With `--brand-check`, the owner's private brand check reads the list and
every line it flags is dropped, so no word of a past client's ships even as a
leaked password. The checker's terms never appear here: only its verdicts
are read. The bundled list was built that way.
"""

from __future__ import annotations

import gzip
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

SHORTEST, LONGEST = 12, 256
#: The name the gzip header holds (the bundled file's, without .gz).
BUNDLED_NAME = "common-passwords.txt"
_DAMAGE = ("�", "пїѕ")


def keep(line: str) -> str | None:
    text = unicodedata.normalize("NFC", line.rstrip("\r\n"))
    if not SHORTEST <= len(text) <= LONGEST:
        return None
    if any(mark in text for mark in _DAMAGE):
        return None
    if any(unicodedata.category(ch) == "Cc" for ch in text):
        return None
    return text.casefold()


def build(sources: list[Path]) -> list[str]:
    seen: dict[str, None] = {}
    for source in sources:
        with source.open(encoding="utf-8", errors="replace") as lines:
            for line in lines:
                kept = keep(line)
                if kept is not None and kept not in seen:
                    seen[kept] = None
    return list(seen)


def brand_flagged(passwords: list[str], checker: Path) -> set[int]:
    """The indexes of the passwords the brand check flags (it prints
    `<file>:<line>: ...` for each)."""
    with tempfile.TemporaryDirectory() as folder:
        listing = Path(folder) / "list.txt"
        listing.write_text("\n".join(passwords) + "\n", "utf-8")
        result = subprocess.run(  # noqa: S603  (the owner's own checker, given on the command line)
            [sys.executable, "-I", str(checker), folder],
            capture_output=True,
            text=True,
            check=False,
        )
    lines = re.findall(r"^list\.txt:(\d+):", result.stdout, flags=re.MULTILINE)
    return {int(line) - 1 for line in lines}


def main(argv: list[str]) -> int:
    checker: Path | None = None
    if "--brand-check" in argv:
        at = argv.index("--brand-check")
        checker = Path(argv[at + 1])
        argv = argv[:at] + argv[at + 2 :]
    if len(argv) < 2:
        print(__doc__)
        return 2
    out, sources = Path(argv[0]), [Path(arg) for arg in argv[1:]]
    passwords = build(sources)
    if checker is not None:
        flagged = brand_flagged(passwords, checker)
        passwords = [p for index, p in enumerate(passwords) if index not in flagged]
        print(f"{len(flagged)} dropped by the brand check")
    # mtime=0 and a fixed name in the header, so the same sources always give
    # the same bytes, whatever OUT is called.
    with (
        out.open("wb") as raw,
        gzip.GzipFile(
            filename=BUNDLED_NAME, fileobj=raw, mode="wb", compresslevel=9, mtime=0
        ) as zipped,
    ):
        zipped.write(("\n".join(passwords) + "\n").encode("utf-8"))
    print(f"{len(passwords)} passwords from {len(sources)} sources written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
