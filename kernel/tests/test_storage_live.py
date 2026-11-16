"""kernel.storage against a real S3-compatible store: what moto can't show.

moto signs links but never checks them. These tests fetch real links, so
they prove the signature, the expiry and the download header hold where the
files will live. They run only when a store is named, and are skipped
otherwise (decision 0032):

    TEST_STORAGE_ENDPOINT_URL      https://<account>.r2.cloudflarestorage.com
    TEST_STORAGE_ACCESS_KEY_ID     a key for the test buckets only
    TEST_STORAGE_SECRET_ACCESS_KEY
    TEST_STORAGE_BUCKET            a private bucket kept for these tests
    TEST_STORAGE_PUBLIC_BUCKET     optional: a public bucket kept for these tests
    TEST_STORAGE_PUBLIC_URL        optional: the address that bucket is served at

Use test buckets, never a site's: each test writes a file under
`kernel-live-test/` and deletes it. The owner types the keys; nothing here
prints them.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import httpx
import pytest

from kernel import storage
from kernel.config import reset_config

LIVE = {
    "STORAGE_ENDPOINT_URL": os.environ.get("TEST_STORAGE_ENDPOINT_URL", ""),
    "STORAGE_ACCESS_KEY_ID": os.environ.get("TEST_STORAGE_ACCESS_KEY_ID", ""),
    "STORAGE_SECRET_ACCESS_KEY": os.environ.get("TEST_STORAGE_SECRET_ACCESS_KEY", ""),
    "STORAGE_BUCKET": os.environ.get("TEST_STORAGE_BUCKET", ""),
    "STORAGE_PUBLIC_BUCKET": os.environ.get("TEST_STORAGE_PUBLIC_BUCKET", ""),
    "STORAGE_PUBLIC_URL": os.environ.get("TEST_STORAGE_PUBLIC_URL", ""),
}
REQUIRED = (
    "STORAGE_ENDPOINT_URL",
    "STORAGE_ACCESS_KEY_ID",
    "STORAGE_SECRET_ACCESS_KEY",
    "STORAGE_BUCKET",
)

pytestmark = [
    pytest.mark.storage_live,
    pytest.mark.skipif(
        not all(LIVE[name] for name in REQUIRED),
        reason="no live store: set TEST_STORAGE_ENDPOINT_URL and its siblings (test_storage_live.py)",
    ),
]

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


@pytest.fixture(autouse=True)
def live(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name, value in LIVE.items():
        monkeypatch.setenv(name, value)
    reset_config()
    storage._client.cache_clear()
    yield
    reset_config()
    storage._client.cache_clear()


async def _fetch(url: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=30) as client:
        return await client.get(url)


async def test_a_signed_link_fetches_the_file_as_a_download() -> None:
    key = storage.unguessable_key("kernel-live-test", ".txt")
    await storage.put(
        key, b"hello from the live test", content_type="text/plain", filename="hello.txt"
    )
    try:
        response = await _fetch(await storage.signed_url(key, filename="hello.txt"))
        assert response.status_code == 200
        assert response.content == b"hello from the live test"
        assert response.headers["content-disposition"].startswith(
            'attachment; filename="hello.txt"'
        )
    finally:
        await storage.delete(key)


async def test_a_tampered_link_is_refused() -> None:
    key = storage.unguessable_key("kernel-live-test", ".txt")
    await storage.put(key, b"secret", content_type="text/plain")
    try:
        url = await storage.signed_url(key)
        stripped = url.replace("response-content-disposition=attachment&", "")
        assert stripped != url
        assert (await _fetch(stripped)).status_code == 403
        other = url.replace(key, storage.unguessable_key("kernel-live-test", ".txt"))
        assert (await _fetch(other)).status_code == 403
    finally:
        await storage.delete(key)


async def test_an_expired_link_is_refused() -> None:
    key = storage.unguessable_key("kernel-live-test", ".txt")
    await storage.put(key, b"brief", content_type="text/plain")
    try:
        url = await storage.signed_url(key, expires_in=1)
        await asyncio.sleep(3)
        assert (await _fetch(url)).status_code == 403
    finally:
        await storage.delete(key)


async def test_a_deleted_file_is_gone() -> None:
    key = storage.unguessable_key("kernel-live-test", ".txt")
    await storage.put(key, b"soon gone", content_type="text/plain")
    await storage.delete(key)
    assert await storage.get(key) is None
    assert (await _fetch(await storage.signed_url(key))).status_code == 404


@pytest.mark.skipif(
    not (LIVE["STORAGE_PUBLIC_BUCKET"] and LIVE["STORAGE_PUBLIC_URL"]),
    reason="no live public bucket: set TEST_STORAGE_PUBLIC_BUCKET and TEST_STORAGE_PUBLIC_URL",
)
async def test_a_public_file_is_at_its_public_address() -> None:
    key = storage.unguessable_key("kernel-live-test", ".png")
    await storage.put(key, PNG, content_type="image/png", public=True)
    try:
        response = await _fetch(storage.public_url(key))
        assert response.status_code == 200
        assert response.content == PNG
        assert response.headers["content-type"] == "image/png"
    finally:
        await storage.delete(key, public=True)
