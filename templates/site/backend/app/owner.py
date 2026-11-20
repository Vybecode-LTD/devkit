"""The site's first owner: `python -m app.owner <email>` (K5 contract §2).

It will make the account and print a one-time link to set its password, so no
password is typed into a terminal (the owner, 2026-11-20). It's built in
MechFrame's next pull request (#94, `kernel.auth.owners.create_owner`); until
then it says so and changes nothing.
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m app.owner <email>")
        return 2
    print(
        "Making the first owner isn't built yet: it arrives with MechFrame's "
        "`mechframe create-owner` (K5, #94).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
