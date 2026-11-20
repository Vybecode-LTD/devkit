"""The site's app builds from its modules and its own pages, and every API
route says who may call it (SPEC.md section 7)."""

from __future__ import annotations

from app import installed
from app.modules import MODULE_IDS
from app.site.pages import SITE_PAGES
from kernel import create_app, server_copy
from kernel.access import undeclared
from kernel.config import KernelConfig


def test_the_app_builds_and_every_route_declares_its_access() -> None:
    app = create_app(modules=installed(MODULE_IDS), config=KernelConfig(), site=SITE_PAGES)
    assert undeclared(app) == []


def test_the_site_owns_its_home_page() -> None:
    app = create_app(modules=installed(MODULE_IDS), config=KernelConfig(), site=SITE_PAGES)
    routes: server_copy.Routes = app.state.public_routes
    assert routes.home_owner(frozenset()) == server_copy.SITE


def test_the_modules_listed_are_the_modules_built() -> None:
    assert [module.id for module in installed(MODULE_IDS)] == list(MODULE_IDS)
