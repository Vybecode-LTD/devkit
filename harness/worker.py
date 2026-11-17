"""The harness's jobs worker as a process of its own (decision 0035):

    python -m harness.worker

The harness's web app runs a worker in its own process already
(JOBS_IN_WEB, on by default); run this one with JOBS_IN_WEB=false on the web
app to try the set-up a site with heavy jobs uses. Run
`python -m harness.migrations upgrade` first. Ctrl-C stops it once its
running jobs finish.
"""

from __future__ import annotations

from harness.registry import discover
from kernel.worker import create_worker, serve


def main() -> int:
    return serve(create_worker(modules=discover()))


if __name__ == "__main__":
    raise SystemExit(main())
