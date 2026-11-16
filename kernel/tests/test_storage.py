"""kernel.storage against moto, an S3 in the test process (decision 0032).

moto answers for the endpoint conftest.py names, as R2 would: path-style,
SigV4, region `auto`. It doesn't check a signed link's signature or expiry;
test_storage_live.py does, against a real store, when one is set.
"""

from __future__ import annotations

import asyncio
import io
import re
import threading
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from moto import mock_aws

from kernel import storage
from kernel.config import reset_config

ENDPOINT = "https://r2.devkit.test"
PRIVATE = "devkit-private"
PUBLIC = "devkit-public"
PUBLIC_URL = "https://files.devkit.test"
KEY_ID = "test-key-id-AKIA0000"
SECRET = "test-secret-do-not-print-8c1f"
STORAGE_ENV = {
    "STORAGE_ENDPOINT_URL": ENDPOINT,
    "STORAGE_ACCESS_KEY_ID": KEY_ID,
    "STORAGE_SECRET_ACCESS_KEY": SECRET,
    "STORAGE_BUCKET": PRIVATE,
    "STORAGE_PUBLIC_BUCKET": PUBLIC,
    "STORAGE_PUBLIC_URL": PUBLIC_URL,
}

#: The first bytes of a real file of each inline type.
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
GIF = b"GIF89a" + b"\x00" * 24
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16
AVIF = b"\x00\x00\x00\x1cftypavif" + b"\x00" * 16
INLINE = {
    "image/png": PNG,
    "image/jpeg": JPEG,
    "image/gif": GIF,
    "image/webp": WEBP,
    "image/avif": AVIF,
}


def _configure(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    for name, value in {**STORAGE_ENV, **overrides}.items():
        monkeypatch.setenv(name, value)
    reset_config()
    storage._client.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_config() -> Iterator[None]:
    reset_config()
    storage._client.cache_clear()
    yield
    reset_config()
    storage._client.cache_clear()


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Both buckets, empty, in a fresh moto; the store's own client."""
    _configure(monkeypatch)
    with mock_aws():
        client = storage._client(ENDPOINT, "auto", KEY_ID, SECRET)
        for bucket in (PRIVATE, PUBLIC):
            client.create_bucket(
                Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": "auto"}
            )
        yield client


def _head(client: Any, key: str, bucket: str = PRIVATE) -> dict[str, Any]:
    head: dict[str, Any] = client.head_object(Bucket=bucket, Key=key)
    return head


# --- off until it's set ------------------------------------------------------------


async def test_every_call_says_storage_is_off_when_nothing_is_set() -> None:
    calls = [
        storage.put("kernel/a.txt", b"x", content_type="text/plain"),
        storage.get("kernel/a.txt"),
        storage.download("kernel/a.txt", io.BytesIO()),
        storage.delete("kernel/a.txt"),
        storage.signed_url("kernel/a.txt"),
    ]
    for call in calls:
        with pytest.raises(storage.StorageNotConfigured) as caught:
            await call
        message = str(caught.value)
        for name in (
            "STORAGE_ENDPOINT_URL",
            "STORAGE_ACCESS_KEY_ID",
            "STORAGE_SECRET_ACCESS_KEY",
            "STORAGE_BUCKET",
        ):
            assert name in message
    with pytest.raises(storage.StorageNotConfigured, match="STORAGE_PUBLIC_URL"):
        storage.public_url("kernel/a.png")


async def test_the_public_bucket_is_off_until_it_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, STORAGE_PUBLIC_BUCKET="", STORAGE_PUBLIC_URL="")
    with pytest.raises(storage.StorageNotConfigured, match="STORAGE_PUBLIC_BUCKET"):
        await storage.put("kernel/a.png", PNG, content_type="image/png", public=True)
    with pytest.raises(storage.StorageNotConfigured, match="STORAGE_PUBLIC_BUCKET"):
        await storage.get("kernel/a.png", public=True)


# --- put, get, download and delete --------------------------------------------------


async def test_a_private_file_round_trips(s3: Any) -> None:
    stored = await storage.put("discography/masters/t1.wav", b"RIFF-wave", content_type="audio/wav")
    assert stored == storage.StoredFile("discography/masters/t1.wav", 9, "audio/wav", inline=False)
    fetched = await storage.get("discography/masters/t1.wav")
    assert fetched == storage.Fetched(b"RIFF-wave", "audio/wav")


async def test_the_two_buckets_are_apart(s3: Any) -> None:
    await storage.put("roster/photos/a.png", PNG, content_type="image/png", public=True)
    assert await storage.get("roster/photos/a.png", public=True) == storage.Fetched(
        PNG, "image/png"
    )
    assert await storage.get("roster/photos/a.png") is None
    assert s3.list_objects_v2(Bucket=PRIVATE).get("KeyCount") == 0


async def test_a_missing_file_is_none_and_downloads_nothing(s3: Any) -> None:
    assert await storage.get("kernel/missing.txt") is None
    into = io.BytesIO()
    assert await storage.download("kernel/missing.txt", into) is False
    assert into.getvalue() == b""


async def test_a_big_file_streams_both_ways(s3: Any) -> None:
    big = bytes(range(256)) * (9 * 4096)  # 9 MiB: over boto3's 8 MiB multipart threshold
    source = io.BytesIO(b"skip" + big)
    source.seek(4)  # put stores from where the file stands
    stored = await storage.put("discography/masters/big.wav", source, content_type="audio/wav")
    assert stored.size == len(big)
    into = io.BytesIO()
    assert await storage.download("discography/masters/big.wav", into) is True
    assert into.getvalue() == big


async def test_get_refuses_a_file_over_its_limit(s3: Any) -> None:
    await storage.put("kernel/ten.bin", b"0123456789", content_type="application/octet-stream")
    with pytest.raises(storage.FileTooLarge):
        await storage.get("kernel/ten.bin", max_bytes=9)
    assert (await storage.get("kernel/ten.bin", max_bytes=10)) is not None
    with pytest.raises(ValueError, match="max_bytes"):
        await storage.get("kernel/ten.bin", max_bytes=0)


async def test_delete_removes_and_is_safe_to_repeat(s3: Any) -> None:
    await storage.put("kernel/gone.txt", b"x", content_type="text/plain")
    await storage.delete("kernel/gone.txt")
    assert await storage.get("kernel/gone.txt") is None
    await storage.delete("kernel/gone.txt")
    await storage.put("kernel/gone.png", PNG, content_type="image/png", public=True)
    await storage.delete("kernel/gone.png", public=True)
    assert await storage.get("kernel/gone.png", public=True) is None


# --- inline or download (SPEC 15) ----------------------------------------------------


@pytest.mark.parametrize("content_type", sorted(INLINE))
async def test_the_five_raster_types_are_inline_when_their_bytes_match(
    s3: Any, content_type: str
) -> None:
    stored = await storage.put("portfolio/p.img", INLINE[content_type], content_type=content_type)
    assert stored.inline is True
    head = _head(s3, "portfolio/p.img")
    assert head["ContentType"] == content_type
    assert head["ContentDisposition"] == "inline"


@pytest.mark.parametrize("content_type", sorted(INLINE))
async def test_an_inline_type_with_other_bytes_is_refused(s3: Any, content_type: str) -> None:
    with pytest.raises(ValueError, match="bytes"):
        await storage.put("portfolio/p.img", b"<html><script>", content_type=content_type)
    assert s3.list_objects_v2(Bucket=PRIVATE).get("KeyCount") == 0


@pytest.mark.parametrize(
    "content_type", ["image/svg+xml", "text/html", "application/pdf", "audio/mpeg", "text/plain"]
)
async def test_everything_else_is_a_download(s3: Any, content_type: str) -> None:
    stored = await storage.put("kernel/f.bin", b"<svg onload=alert(1)>", content_type=content_type)
    assert stored.inline is False
    assert _head(s3, "kernel/f.bin")["ContentDisposition"] == "attachment"


async def test_a_download_carries_its_file_name_safely(s3: Any) -> None:
    await storage.put(
        "licensing/stems/s.zip",
        b"PK",
        content_type="application/zip",
        # Quotes, CR LF, slashes, NUL and a right-to-left override (which can
        # disguise an extension) all become spaces.
        filename='Beat "One"\r\n\\/' + chr(0x202E) + chr(0) + "é.zip",
    )
    disposition = _head(s3, "licensing/stems/s.zip")["ContentDisposition"]
    assert (
        disposition
        == "attachment; filename=\"Beat One e.zip\"; filename*=UTF-8''Beat%20One%20%C3%A9.zip"
    )


async def test_an_unusable_file_name_falls_back(s3: Any) -> None:
    await storage.put("kernel/n.txt", b"x", content_type="text/plain", filename='\r\n"\\/')
    assert _head(s3, "kernel/n.txt")["ContentDisposition"] == "attachment"
    await storage.put("kernel/m.txt", b"x", content_type="text/plain", filename="日本")
    assert _head(s3, "kernel/m.txt")["ContentDisposition"] == (
        "attachment; filename=\"download\"; filename*=UTF-8''%E6%97%A5%E6%9C%AC"
    )


@pytest.mark.parametrize(
    ("filename", "fallback"),
    [
        # Fullwidth quotes and a fullwidth backslash become ASCII ones when the
        # ASCII fallback is normalized: they must not end or escape its quotes.
        (
            "Beat" + chr(0xFF02) + "; filename=" + chr(0xFF02) + "other.exe",
            "Beat ; filename= other.exe",
        ),
        ("Beat" + chr(0xFF3C), "Beat"),
        ("a" + chr(0xFF0F) + "b.zip", "a b.zip"),
    ],
)
async def test_a_fullwidth_quote_cannot_add_a_file_name(
    s3: Any, filename: str, fallback: str
) -> None:
    await storage.put("kernel/w.zip", b"PK", content_type="application/zip", filename=filename)
    disposition = _head(s3, "kernel/w.zip")["ContentDisposition"]
    assert disposition.startswith(f"attachment; filename=\"{fallback}\"; filename*=UTF-8''")
    # Two quotes only: the ASCII name's own, so nothing inside ends it early.
    assert disposition.count('"') == 2
    assert "\\" not in disposition
    url = await storage.signed_url("kernel/w.zip", filename=filename)
    assert parse_qs(urlsplit(url).query)["response-content-disposition"] == [disposition]


# --- refused before any call ---------------------------------------------------------

BAD_KEYS = [
    "",
    "/a",
    "a/",
    "a//b",
    "../a",
    "a/../b",
    "./a",
    ".hidden",
    "a b",
    "a\nb",
    "a\\b",
    "ä/b",
    "a/" + "b" * 129,
    "/".join(["abcdefg"] * 64) + "xy",  # 513: 512 is the most
]


@pytest.mark.parametrize("key", BAD_KEYS)
async def test_a_bad_key_is_refused_before_anything_else(key: str) -> None:
    # Storage is off here: the key is checked first, so the caller's bug shows.
    with pytest.raises(ValueError, match="key"):
        await storage.put(key, b"x", content_type="text/plain")
    with pytest.raises(ValueError, match="key"):
        await storage.get(key)
    with pytest.raises(ValueError, match="key"):
        await storage.download(key, io.BytesIO())
    with pytest.raises(ValueError, match="key"):
        await storage.delete(key)
    with pytest.raises(ValueError, match="key"):
        await storage.signed_url(key)
    with pytest.raises(ValueError, match="key"):
        storage.public_url(key)


def test_the_longest_key_passes() -> None:
    longest = "/".join(["abcdefg"] * 64)
    assert len(longest) == 511
    storage.check_key(longest + "x")


@pytest.mark.parametrize(
    "content_type",
    [
        "",
        "png",
        "image/",
        "/png",
        "IMAGE/PNG",
        "image/png; charset=x",
        "text/html\r\nX-A: b",
        "a/b/c",
        "image/ png",
    ],
)
async def test_a_bad_content_type_is_refused(content_type: str) -> None:
    with pytest.raises(ValueError, match="content type"):
        await storage.put("kernel/a.bin", b"x", content_type=content_type)


async def test_a_file_over_the_limit_is_refused(s3: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, STORAGE_MAX_BYTES="10")
    with pytest.raises(storage.FileTooLarge, match="10"):
        await storage.put("kernel/a.bin", b"01234567890", content_type="application/octet-stream")
    with pytest.raises(storage.FileTooLarge):
        await storage.put(
            "kernel/a.bin", io.BytesIO(b"01234567890"), content_type="application/octet-stream"
        )
    await storage.put("kernel/a.bin", b"0123456789", content_type="application/octet-stream")


async def test_a_file_that_cannot_seek_is_refused() -> None:
    class Pipe(io.RawIOBase):
        def readable(self) -> bool:
            return True

    with pytest.raises(ValueError, match="that can seek, so its size is known"):
        await storage.put("kernel/a.bin", Pipe(), content_type="application/octet-stream")  # type: ignore[arg-type]


# --- links -------------------------------------------------------------------------


async def test_a_signed_link_is_short_lived_and_always_a_download(s3: Any) -> None:
    url = await storage.signed_url("licensing/stems/s.zip")
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == ENDPOINT
    assert parts.path == f"/{PRIVATE}/licensing/stems/s.zip"
    query = parse_qs(parts.query)
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert query["response-content-disposition"] == ["attachment"]
    assert "X-Amz-Signature" in query
    assert SECRET not in url

    named = await storage.signed_url("licensing/stems/s.zip", expires_in=21600, filename="Beat.zip")
    named_query = parse_qs(urlsplit(named).query)
    assert named_query["X-Amz-Expires"] == ["21600"]
    assert named_query["response-content-disposition"] == [
        "attachment; filename=\"Beat.zip\"; filename*=UTF-8''Beat.zip"
    ]


@pytest.mark.parametrize("seconds", [0, -1, 21601])
async def test_a_signed_link_lives_one_second_to_six_hours(s3: Any, seconds: int) -> None:
    with pytest.raises(ValueError, match="expires_in"):
        await storage.signed_url("kernel/a.txt", expires_in=seconds)
    await storage.signed_url("kernel/a.txt", expires_in=1)


async def test_a_pasted_bucket_url_still_reaches_the_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, STORAGE_ENDPOINT_URL=f"{ENDPOINT}/{PRIVATE}/")
    with mock_aws():
        url = await storage.signed_url("kernel/a.txt")
    assert url.startswith(f"{ENDPOINT}/{PRIVATE}/kernel/a.txt?")


def test_a_public_link_is_the_public_address(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, STORAGE_PUBLIC_URL=PUBLIC_URL + "/")
    assert (
        storage.public_url("discography/stream/t1.mp3") == f"{PUBLIC_URL}/discography/stream/t1.mp3"
    )


def test_an_unguessable_key_is_long_random_and_valid() -> None:
    keys = {storage.unguessable_key("print-on-demand/print-files", ".png") for _ in range(1000)}
    assert len(keys) == 1000
    for key in keys:
        assert re.fullmatch(r"print-on-demand/print-files/[A-Za-z0-9_-]{32}\.png", key)
        storage.check_key(key)
    assert re.fullmatch(r"kernel/[A-Za-z0-9_-]{32}", storage.unguessable_key("kernel"))


@pytest.mark.parametrize("suffix", ["png", ".p/ng", ".abcdefghijk", ". ", ".png\n"])
def test_an_unguessable_key_takes_only_a_plain_suffix(suffix: str) -> None:
    with pytest.raises(ValueError, match="suffix"):
        storage.unguessable_key("kernel", suffix)
    with pytest.raises(ValueError, match="key"):
        storage.unguessable_key("../kernel")


# --- the client, threads and failures ------------------------------------------------


def test_the_client_is_set_up_for_r2() -> None:
    client = storage._client(ENDPOINT, "auto", KEY_ID, SECRET)
    config = client.meta.config
    assert config.signature_version == "s3v4"
    assert config.s3 == {"addressing_style": "path"}
    assert config.region_name == "auto"
    assert config.connect_timeout == 5
    assert config.read_timeout == 60
    assert config.retries == {"total_max_attempts": 3, "mode": "standard"}
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"
    assert client.meta.endpoint_url == ENDPOINT


async def test_the_store_is_called_off_the_event_loop(s3: Any) -> None:
    loop_thread = threading.get_ident()
    seen: list[int] = []

    def record(**_: Any) -> None:
        seen.append(threading.get_ident())

    s3.meta.events.register("before-call.s3", record)
    try:
        await storage.put("kernel/t.txt", b"x", content_type="text/plain")
        await storage.get("kernel/t.txt")
        await storage.download("kernel/t.txt", io.BytesIO())
        await storage.delete("kernel/t.txt")
    finally:
        s3.meta.events.unregister("before-call.s3", record)
    assert seen
    assert loop_thread not in seen


async def test_a_store_failure_says_what_failed_and_nothing_secret(s3: Any) -> None:
    s3.delete_bucket(Bucket=PRIVATE)
    for call in (
        storage.put("kernel/a.txt", b"x", content_type="text/plain"),
        storage.get("kernel/a.txt"),
        storage.download("kernel/a.txt", io.BytesIO()),
    ):
        with pytest.raises(storage.StorageError, match="NoSuchBucket") as caught:
            await call
        assert SECRET not in str(caught.value)
        assert KEY_ID not in str(caught.value)


async def test_an_unreachable_store_is_a_storage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Port 9 on loopback: nothing listens, so the connection is refused at once.
    _configure(monkeypatch, STORAGE_ENDPOINT_URL="https://127.0.0.1:9")
    with pytest.raises(storage.StorageError, match="reach"):
        await asyncio.wait_for(storage.get("kernel/a.txt"), timeout=30)


def test_the_kernel_exports_storage() -> None:
    import kernel

    assert kernel.storage is storage
    assert "storage" in kernel.__all__
