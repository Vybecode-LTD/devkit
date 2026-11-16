---
feature: K3 storage (kernel.storage)
status: approved
approved: 2026-11-16 (the owner, with the two-bucket set-up)
plan: dev plans/2026-11-16-next-session-k3-storage.md (section 4, item 3)
pr: 58
---

# Contract: K3 storage (`kernel.storage`)

## 1. Goal

A module or a job can keep files in S3-compatible storage (Cloudflare R2) and hand them out safely. Private files are reached only through short-lived signed links. Public files, such as stream files and photos, sit at a stable public address. A file an outside provider must fetch gets an unguessable public key that the module deletes when the job ends (SPEC 15).

## 2. Interfaces

`kernel/backend/kernel/storage.py`, public as `from kernel import storage`. Every call that reaches the store runs boto3 in `asyncio.to_thread`, so nothing blocks the event loop. `public=True` selects the public bucket; the default is the private one.

```python
async def put(key: str, data: bytes | BinaryIO, *, content_type: str, public: bool = False,
              filename: str | None = None) -> StoredFile        # StoredFile(key, size, content_type, inline)
async def get(key: str, *, public: bool = False, max_bytes: int = 32 * 1024 * 1024) -> Fetched | None
                                                                 # Fetched(data, content_type); None if absent
async def download(key: str, into: BinaryIO, *, public: bool = False) -> bool   # streams; False if absent
async def delete(key: str, *, public: bool = False) -> None      # no error if already gone
async def signed_url(key: str, *, expires_in: int = 300, filename: str | None = None) -> str
                                                                 # private bucket only; 1 s to 6 h
def public_url(key: str) -> str                                  # STORAGE_PUBLIC_URL + the quoted key
def unguessable_key(prefix: str, suffix: str = "") -> str        # f"{prefix}/{192-bit token}{suffix}"
def check_key(key: str) -> None                                 # ValueError unless the key follows the rules below
class StorageNotConfigured(RuntimeError)   # names the missing variables, never their values
class StorageError(RuntimeError)           # the store refused or failed; carries the S3 error code only
class FileTooLarge(ValueError)
```

- **Keys:** 1 to 512 characters; `/`-separated segments of `[A-Za-z0-9._-]`, each 1 to 128 long and starting with a letter, digit, `_` or `-` (so `.` and `..` are impossible); no leading or trailing `/`. By convention a key starts with its module's id (`discography/masters/…`). A bad key is `ValueError`.
- **Content type:** one lowercase `type/subtype`, no parameters, no line breaks.
- **Inline or download (SPEC 15):** only `image/png`, `image/jpeg`, `image/gif`, `image/webp` and `image/avif` are stored inline, and only when the bytes start with that format's signature (otherwise `ValueError`). Everything else, SVG included, is stored with `Content-Disposition: attachment` (plus the RFC 6266 `filename*` when given). `signed_url` always signs `attachment` (with the file name when given) into the link, so whoever holds it can't strip it; `<img>`, `<audio>` and `<video>` still play it.
- **Size:** `put` refuses anything over `STORAGE_MAX_BYTES` (default 2 GiB); `get` refuses anything over `max_bytes` before reading it. Use `download` for big files (a job feeding ffmpeg).
- **Client:** path-style addressing, SigV4, region `auto`, checksums only when required (R2), a 5 s connect and 60 s read timeout, and 3 tries. The endpoint is cut back to scheme, host and port, so a pasted bucket URL still works (Basefra.me's lesson).

**Config** (`KernelConfig`, environment variables): `STORAGE_ENDPOINT_URL`, `STORAGE_REGION` (`auto`), `STORAGE_ACCESS_KEY_ID`, `STORAGE_SECRET_ACCESS_KEY` (a `SecretStr`), `STORAGE_BUCKET`, `STORAGE_PUBLIC_BUCKET`, `STORAGE_PUBLIC_URL`, `STORAGE_MAX_BYTES`. If none are set, storage is off and each call raises `StorageNotConfigured`. If some are set, `refuse_unsafe` stops the start (outside DEBUG) on any of these: a missing endpoint, key or bucket; an endpoint that isn't https; a public bucket without its URL, or the reverse; a public URL that isn't https or is a placeholder; or the same bucket used for both.

## 3. Data

None. Modules keep their keys in their own tables (for example `discography_track.file_key` and `stream_key`).

## 4. Files

- New: `kernel/backend/kernel/storage.py`, `kernel/tests/test_storage.py` (moto), `kernel/tests/test_storage_live.py` (opt-in), `docs/decisions/0032-kernel-storage.md`.
- Changed: `kernel/backend/kernel/config.py` (fields, `storage_problems`, `refuse_unsafe`), `kernel/backend/kernel/__init__.py`, `kernel/tests/test_config.py`, `requirements.in` (boto3), `requirements-dev.in` (moto), both `.txt` re-pinned, `pyproject.toml` (the `storage_live` marker), `.env.example`, `SPEC.md` (section 6 row and change log), `CLAUDE.md`/`AGENTS.md` (Stack), `docs/TESTING.md`, `docs/HANDOFF.md`, `NOTICE` if a license needs it.

## 5. Conventions this follows

`kernel/backend/kernel/crypto.py` (module-level calls on `get_config()`), `kernel/backend/kernel/email.py` (checks that name the field, never the value), `kernel/backend/kernel/config.py` (`refuse_unsafe`). Lifted from Basefra.me `backend/app/storage/service.py` and VybeSite `backend/app/backup.py`; VybeSite's brand check runs on the result.

## 6. Non-goals

- No uploads straight from the browser (signed PUT): they arrive with discography's upload in the site's step 2. R2 has no POST policy, so they'll use a signed PUT.
- No type detection beyond the inline-image check, and no Pillow re-encoding or metadata stripping. That's upload handling (SPEC 15, Uploads), which comes with the first module that takes images.
- No HTTP routes, no table of files, and no listing, quotas, lifecycle rules or CDN purge.
- No real R2 set-up: the owner makes the buckets and types the keys on the host.

## 7. Acceptance

- `kernel/tests/test_storage.py`, against moto: put and get round trip, both buckets; `get` misses as `None`; `download` streams and reports a miss; `delete` is idempotent; inline only for the five raster types with matching bytes; SVG, HTML and mismatched bytes go out as attachment or are refused; `filename*` is encoded; bad keys, bad types and oversize data are refused before any call; `signed_url` refuses the public bucket, signs its expiry and disposition, and keeps to 1 s to 6 h; `public_url` quotes the key; `unguessable_key`'s shape and uniqueness; the boto3 calls run off the event loop's thread; unconfigured calls raise `StorageNotConfigured`; store failures become `StorageError` without the secret.
- `kernel/tests/test_config.py`: each case of `storage_problems`, and that no message holds a value.
- `kernel/tests/test_storage_live.py` (marker `storage_live`; skipped unless `TEST_STORAGE_ENDPOINT_URL` and its siblings are set): a signed link fetches the file with its disposition; a tampered or expired link gets 403; a public file is fetched from `STORAGE_PUBLIC_URL`; a deleted file's link gets 404.
- The full suite stays green, coverage holds at 95% or more, and `kernel/storage.py` is at 100%.

## 8. Open questions

None. The owner approved the goal, the non-goals and the two-bucket set-up on 2026-11-16, and chose moto plus an opt-in live test for the tests.

## Changes after approval

- 2026-11-16: `check_key` is public, so a module can check a key it builds from user input before using it.
- 2026-11-16: `signed_url` always signs `attachment` (with the file name when given) instead of the disposition stored with the file, so it needs no request to the store first; `<img>`, `<audio>` and `<video>` still play it.
- 2026-11-16: "3 tries" is `total_max_attempts: 3`; botocore's `max_attempts` counts retries only, so 3 would have been four tries.
