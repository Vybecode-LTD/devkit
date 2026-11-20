"""The mechframe CLI (K5 contract, `dev plans/contracts/k5-cli-and-site-template.md`).

It makes sites from this MechFrame checkout and checks them against it
(SPEC.md sections 12 and 13). Run it as `python -m mechframe`, or, after
`python -m pip install -e .`, as `mechframe` or `mf` (decision 0034).
"""

from __future__ import annotations

#: MechFrame's own version, written into every lock file and the catalog.
__version__ = "0.1.0"
