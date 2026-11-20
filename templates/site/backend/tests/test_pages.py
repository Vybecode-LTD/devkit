"""What the site's addresses answer, as SPEC.md section 9 says: its home page
with its words and JSON-LD, a kernel page as the shell with noindex, and a
real 404 for an address it doesn't have."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from fastapi import FastAPI

from app import installed
from app.modules import MODULE_IDS
from app.site.pages import SITE_PAGES
from kernel import create_app
from kernel.config import KernelConfig

NOINDEX = '<meta name="robots" content="noindex"'


@pytest_asyncio.fixture(loop_scope="session")
async def client(migrated_url: str) -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(
        modules=installed(MODULE_IDS),
        config=KernelConfig(database_url=migrated_url),
        site=SITE_PAGES,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="https://site.test") as found:
            yield found


def _title(text: str) -> str:
    found = re.search(r"<title>(.*?)</title>", text)
    assert found is not None, text
    return found.group(1)


async def test_the_home_page_is_the_sites_own_with_its_words(client: httpx.AsyncClient) -> None:
    home = await client.get("/")
    assert home.status_code == 200
    assert _title(home.text) == "Test Site"
    assert "<h1>Test Site</h1>" in home.text
    assert '"@type": "Organization"' in home.text
    assert '<link rel="canonical" href="https://site.test/"' in home.text
    assert NOINDEX not in home.text


async def test_sign_in_is_the_shell_titled_and_not_indexed(client: httpx.AsyncClient) -> None:
    page = await client.get("/sign-in")
    assert page.status_code == 200
    assert _title(page.text) == "Sign in · Test Site"
    assert NOINDEX in page.text


async def test_an_address_the_site_doesnt_have_is_a_real_404(client: httpx.AsyncClient) -> None:
    missing = await client.get("/nowhere")
    assert missing.status_code == 404
    assert NOINDEX in missing.text


async def test_the_kernels_files_list_the_home_page(client: httpx.AsyncClient) -> None:
    sitemap = await client.get("/sitemap.xml")
    robots = await client.get("/robots.txt")
    assert "<loc>https://site.test/</loc>" in sitemap.text
    assert "Sitemap: https://site.test/sitemap.xml" in robots.text


async def test_the_health_check_answers(client: httpx.AsyncClient) -> None:
    health = await client.get("/api/kernel/health")
    assert health.status_code == 200
