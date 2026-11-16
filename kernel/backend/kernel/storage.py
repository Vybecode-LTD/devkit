"""Object storage for modules and jobs (SPEC.md sections 6 and 15; decision 0032).

Lifted from Basefra.me `backend/app/storage/service.py` and VybeSite
`backend/app/backup.py`: boto3 against an S3-compatible store, Cloudflare R2
on a live site, set up the way R2 needs (path-style addressing, SigV4, region
`auto`, checksums only when required). The contract is
`dev plans/contracts/k3-storage.md`.

- **Two buckets.** `STORAGE_BUCKET` is private: its files are reached only
  through `signed_url`, a link that lives from 1 second to 6 hours (5 minutes
  unless asked). `STORAGE_PUBLIC_BUCKET` is served to anyone at
  `STORAGE_PUBLIC_URL`: stream files and photos. A file an outside provider
  fetches, such as a print file, goes in the public bucket under
  `unguessable_key`, and its module deletes it when the job ends.
- **Inline or download** (SPEC 15). Only PNG, JPEG, GIF, WebP and AVIF whose
  bytes match are stored inline. Everything else, SVG included, is stored as an
  attachment, and every signed link signs `attachment` in, so a page uploaded
  as a file never renders on the store's address. `<img>`, `<audio>` and
  `<video>` still play an attachment.
- **Keys** follow `check_key`; a module's keys start with its id. A bad key, a
  bad content type or a file that can't seek is the caller's bug: ValueError,
  raised before anything else.
- **Off the event loop.** boto3 is synchronous, so every call that reaches the
  store runs in `asyncio.to_thread`. A call in flight can't be cancelled; the
  client's timeouts and its three tries bound it.
- **Failures.** A missing file is `None` (`get`) or `False` (`download`). Any
  other failure is `StorageError`, which carries the store's error code and
  never a key or a secret. With nothing set, every call raises
  `StorageNotConfigured`, naming the variables to set.
"""

from __future__ import annotations

import asyncio
import io
import re
import secrets
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, BinaryIO
from urllib.parse import quote, urlsplit

import boto3
from boto3.exceptions import Boto3Error
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from kernel.config import get_config, storage_missing

MAX_KEY = 512
#: What `get` reads at most unless told otherwise; `download` streams any size.
DEFAULT_GET_MAX = 32 * 1024 * 1024
DEFAULT_LINK_SECONDS = 5 * 60
MAX_LINK_SECONDS = 6 * 60 * 60
#: The longest file name a download carries.
MAX_FILENAME = 150

_SEGMENT = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]{0,127}")
_CONTENT_TYPE = re.compile(r"[a-z0-9][a-z0-9!#$&^_.+-]{0,126}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}")
_SUFFIX = re.compile(r"(?:\.[A-Za-z0-9]{1,10})?")
#: The codes a store answers with for a file that isn't there (a GET's and a HEAD's).
_MISSING = frozenset({"NoSuchKey", "404", "NotFound"})
#: Enough of a file's start to tell the inline formats apart.
_HEAD_BYTES = 16

#: The formats stored inline, each with a test of the bytes its files start with.
INLINE_IMAGES: dict[str, Callable[[bytes], bool]] = {
    "image/png": lambda head: head.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda head: head.startswith(b"\xff\xd8\xff"),
    "image/gif": lambda head: head[:6] in (b"GIF87a", b"GIF89a"),
    "image/webp": lambda head: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
    "image/avif": lambda head: head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"),
}


class StorageNotConfigured(RuntimeError):
    """Storage, or its public bucket, is off: the message names what to set."""


class StorageError(RuntimeError):
    """The store refused or couldn't be reached. Says which, with the store's
    error code, and nothing of the key or the credentials."""


class FileTooLarge(ValueError):
    """A file over STORAGE_MAX_BYTES (put) or over `max_bytes` (get)."""


@dataclass(frozen=True)
class StoredFile:
    key: str
    size: int
    content_type: str
    inline: bool


@dataclass(frozen=True)
class Fetched:
    data: bytes
    content_type: str


def check_key(key: str) -> None:
    """Raises ValueError unless `key` is a storage key: 1 to 512 characters of
    `/`-separated segments, each 1 to 128 of letters, digits, `.`, `_` and `-`,
    not starting with `.` (so `.` and `..` can't appear)."""
    if not 1 <= len(key) <= MAX_KEY or not all(_SEGMENT.fullmatch(part) for part in key.split("/")):
        raise ValueError(
            "A storage key is 1 to 512 characters of /-separated segments, each 1 to 128 "
            "letters, digits, '.', '_' or '-', not starting with '.'."
        )


def unguessable_key(prefix: str, suffix: str = "") -> str:
    """`prefix` plus a random 192-bit segment and `suffix`, for a public file
    nobody should find without being given its address."""
    check_key(prefix)
    if not _SUFFIX.fullmatch(suffix):
        raise ValueError(
            "An unguessable key's suffix is blank, or a dot and 1 to 10 letters or digits (.png)."
        )
    key = f"{prefix}/{secrets.token_urlsafe(24)}{suffix}"
    check_key(key)
    return key


def _check_type(content_type: str) -> None:
    if not _CONTENT_TYPE.fullmatch(content_type):
        raise ValueError(
            "A file's content type is one lowercase type/subtype, such as image/png, with no parameters."
        )


def _clean_name(text: str) -> str:
    """`text` with control characters, line breaks, quotes, backslashes and
    slashes as spaces, and runs of space as one."""
    cleaned = "".join(
        (
            " "
            if character in '"\\/'
            or unicodedata.category(character)[0] == "C"
            or unicodedata.category(character) in ("Zl", "Zp")
            else character
        )
        for character in text
    )
    return " ".join(cleaned.split())


def _attachment(filename: str | None) -> str:
    """`attachment`, with the file name (RFC 6266) when there's a usable one:
    control characters, quotes and slashes become spaces, and an ASCII
    `filename` goes before the UTF-8 `filename*` for old clients. The ASCII
    form is cleaned again after it's made, since normalizing turns fullwidth
    quotes and backslashes (U+FF02, U+FF3C) into ones that would end or escape
    it."""
    if filename is None:
        return "attachment"
    name = _clean_name(filename)[:MAX_FILENAME].strip()
    if not name:
        return "attachment"
    fallback = _clean_name(
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    return f"attachment; filename=\"{fallback or 'download'}\"; filename*=UTF-8''{quote(name, safe='')}"


def _source(data: bytes | BinaryIO) -> tuple[BinaryIO, int, bytes]:
    """The file to send, its size from where it stands, and its first bytes."""
    if isinstance(data, bytes | bytearray | memoryview):
        raw = bytes(data)
        return io.BytesIO(raw), len(raw), raw[:_HEAD_BYTES]
    if not data.seekable():
        raise ValueError(
            "A file put in storage is bytes or a binary file that can seek, so its size is known first."
        )
    start = data.tell()
    end = data.seek(0, io.SEEK_END)
    data.seek(start)
    head = data.read(_HEAD_BYTES)
    data.seek(start)
    return data, end - start, head


def _endpoint(url: str) -> str:
    """Scheme, host and port only: a bucket path pasted onto R2's endpoint
    would otherwise be doubled into every request (Basefra.me's lesson)."""
    parts = urlsplit(url.strip())
    return f"{parts.scheme}://{parts.netloc}"


@lru_cache(maxsize=4)
def _client(endpoint: str, region: str, key_id: str, secret: str) -> Any:
    """The store's client, made once per set of credentials. Its own session,
    so boto3's shared default is never touched from two threads."""
    return boto3.session.Session().client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=60,
            retries={"total_max_attempts": 3, "mode": "standard"},  # three tries in all
            # boto3 1.36+ sends checksum headers R2 has refused; send them only
            # when an operation requires them.
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def _configured(public: bool) -> tuple[Any, str, int]:
    """The client, the bucket for `public`, and STORAGE_MAX_BYTES."""
    config = get_config()
    missing = storage_missing(config)
    if missing:
        raise StorageNotConfigured(f"Storage is off: set {', '.join(missing)} (kernel.storage).")
    bucket = (config.storage_public_bucket if public else config.storage_bucket).strip()
    if not bucket:
        raise StorageNotConfigured(
            "The public bucket is off: set STORAGE_PUBLIC_BUCKET and STORAGE_PUBLIC_URL."
        )
    client = _client(
        _endpoint(config.storage_endpoint_url),
        config.storage_region.strip() or "auto",
        config.storage_access_key_id.strip(),
        config.storage_secret_access_key.get_secret_value().strip(),
    )
    return client, bucket, config.storage_max_bytes


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code") or "unknown")


async def _call[T](action: str, function: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """`function` on a worker thread, its store failures as StorageError."""
    try:
        return await asyncio.to_thread(function, *args, **kwargs)
    except ClientError as error:
        raise StorageError(f"The store refused to {action}: {_code(error)}.") from error
    except (BotoCoreError, Boto3Error) as error:
        cause = error.__cause__ or error.__context__
        if isinstance(cause, ClientError):
            raise StorageError(f"The store refused to {action}: {_code(cause)}.") from error
        raise StorageError(
            f"Couldn't reach the store to {action} ({type(error).__name__})."
        ) from error


async def put(
    key: str,
    data: bytes | BinaryIO,
    *,
    content_type: str,
    public: bool = False,
    filename: str | None = None,
) -> StoredFile:
    """Stores `data` at `key`, replacing what was there. A file object is read
    from where it stands, in parts when it's big. `filename` names the
    download; an inline image ignores it."""
    check_key(key)
    _check_type(content_type)
    disposition = _attachment(filename)
    body, size, head = _source(data)
    inline = content_type in INLINE_IMAGES
    if inline and not INLINE_IMAGES[content_type](head):
        raise ValueError(
            f"The bytes aren't {content_type}: a file stored inline must be what it says."
        )
    client, bucket, max_bytes = _configured(public)
    if size > max_bytes:
        raise FileTooLarge(f"The file is {size} bytes; STORAGE_MAX_BYTES allows {max_bytes}.")
    extra = {"ContentType": content_type, "ContentDisposition": "inline" if inline else disposition}
    await _call("store a file", client.upload_fileobj, body, bucket, key, ExtraArgs=extra)
    return StoredFile(key, size, content_type, inline)


async def get(
    key: str, *, public: bool = False, max_bytes: int = DEFAULT_GET_MAX
) -> Fetched | None:
    """The file at `key`, or None if there's none. Refuses a file over
    `max_bytes` before reading it: use `download` for big files."""
    check_key(key)
    if max_bytes < 1:
        raise ValueError("get's max_bytes is at least 1.")
    client, bucket, _ = _configured(public)

    def fetch() -> Fetched | None:
        try:
            answer = client.get_object(Bucket=bucket, Key=key)
        except ClientError as error:
            if _code(error) in _MISSING:
                return None
            raise
        body = answer["Body"]
        try:
            if int(answer.get("ContentLength") or 0) > max_bytes:
                raise FileTooLarge(
                    f"The file is over get's max_bytes ({max_bytes}): use storage.download."
                )
            return Fetched(
                body.read(), str(answer.get("ContentType") or "application/octet-stream")
            )
        finally:
            body.close()

    return await _call("read a file", fetch)


async def download(key: str, into: BinaryIO, *, public: bool = False) -> bool:
    """Streams the file at `key` into `into`; False if there's none. After a
    StorageError, `into` may hold part of the file: discard it."""
    check_key(key)
    client, bucket, _ = _configured(public)

    def fetch() -> bool:
        try:
            client.download_fileobj(bucket, key, into)
        except ClientError as error:
            if _code(error) in _MISSING:
                return False
            raise
        return True

    return await _call("read a file", fetch)


async def delete(key: str, *, public: bool = False) -> None:
    """Removes the file at `key`. No error if it's already gone."""
    check_key(key)
    client, bucket, _ = _configured(public)
    await _call("delete a file", client.delete_object, Bucket=bucket, Key=key)


async def signed_url(
    key: str, *, expires_in: int = DEFAULT_LINK_SECONDS, filename: str | None = None
) -> str:
    """A link to the private file at `key` that works for `expires_in`
    seconds (1 to 6 hours) and always downloads: the signature covers the
    `attachment` header, so whoever holds the link can't strip it. Signing
    is local; it doesn't check that the file exists."""
    check_key(key)
    if not 1 <= expires_in <= MAX_LINK_SECONDS:
        raise ValueError(f"A signed link's expires_in is 1 to {MAX_LINK_SECONDS} seconds.")
    disposition = _attachment(filename)
    client, bucket, _ = _configured(public=False)
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key, "ResponseContentDisposition": disposition},
        ExpiresIn=expires_in,
    )
    return str(url)


def public_url(key: str) -> str:
    """The address anyone can fetch the public file at `key` from."""
    check_key(key)
    base = get_config().storage_public_url.strip().rstrip("/")
    if not base:
        raise StorageNotConfigured(
            "Public links are off: set STORAGE_PUBLIC_BUCKET and STORAGE_PUBLIC_URL."
        )
    return f"{base}/{quote(key, safe='/')}"
