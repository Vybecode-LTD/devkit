"""crypto.seal / open, with keys that rotate (SPEC.md 14.12)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography.fernet import Fernet

from kernel import crypto
from kernel.config import reset_config


class Keys:
    """Two keys of the test's own, and a way to set ENCRYPTION_KEYS from them."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.old = Fernet.generate_key().decode()
        self.new = Fernet.generate_key().decode()
        self._monkeypatch = monkeypatch
        self.use(self.old)

    def use(self, *keys: str) -> None:
        self._monkeypatch.setenv("ENCRYPTION_KEYS", ",".join(keys))
        reset_config()


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[Keys]:
    yield Keys(monkeypatch)
    monkeypatch.undo()
    reset_config()


def test_seal_and_open(keys: Keys) -> None:
    sealed = crypto.seal("sk_live_123")
    assert "sk_live_123" not in sealed
    assert crypto.open(sealed) == "sk_live_123"
    assert crypto.seal("sk_live_123") != sealed  # a fresh IV each time


def test_rotation(keys: Keys) -> None:
    sealed = crypto.seal("token")
    keys.use(keys.new, keys.old)
    assert crypto.open(sealed) == "token"
    assert not crypto.sealed_with_newest(sealed)
    resealed = crypto.rotate(sealed)
    assert crypto.sealed_with_newest(resealed)
    keys.use(keys.new)
    assert crypto.open(resealed) == "token"
    with pytest.raises(crypto.SealError, match="can't be opened"):
        crypto.open(sealed)


def test_tampered_or_garbage_is_refused(keys: Keys) -> None:
    sealed = crypto.seal("token")
    with pytest.raises(crypto.SealError):
        crypto.open(sealed[:-4] + "AAAA")
    with pytest.raises(crypto.SealError):
        crypto.open("not sealed at all")
    with pytest.raises(crypto.SealError):
        crypto.rotate("ünïcode")


def test_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENCRYPTION_KEYS", "")
    reset_config()
    try:
        with pytest.raises(crypto.SealError, match="ENCRYPTION_KEYS is empty"):
            crypto.seal("x")
        assert not crypto.sealed_with_newest("x")
    finally:
        monkeypatch.undo()
        reset_config()
