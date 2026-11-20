"""This site's jobs worker as a process of its own (decision 0035):

    python -m app.worker                        (with PYTHONPATH=backend)

The web app runs a worker in its own process already (JOBS_IN_WEB, on by
default). A site with heavy jobs runs this as a second service and sets
JOBS_IN_WEB=false on the web one. Ctrl-C stops it once its running jobs finish.
"""

from __future__ import annotations

from app import installed
from app.modules import MODULE_IDS
from kernel.worker import create_worker, serve


def main() -> int:
    return serve(create_worker(modules=installed(MODULE_IDS)))


if __name__ == "__main__":
    raise SystemExit(main())
