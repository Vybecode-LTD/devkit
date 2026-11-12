"""The test-support routes are mounted only on request, never by harness.main."""

from __future__ import annotations

import pytest

from harness import testing


def test_refused_without_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HARNESS_TEST_SUPPORT", raising=False)
    with pytest.raises(RuntimeError, match="HARNESS_TEST_SUPPORT=1"):
        testing.build_test_app()


def test_the_plain_harness_has_no_test_routes(
    monkeypatch: pytest.MonkeyPatch, migrated_url: str
) -> None:
    import importlib

    from kernel.config import reset_config

    monkeypatch.setenv("DATABASE_URL", migrated_url)
    reset_config()
    try:
        main = importlib.reload(importlib.import_module("harness.main"))
        paths = {getattr(route, "path", "") for route in main.app.routes}
        assert not any(path.startswith("/api/_test") for path in paths)
    finally:
        reset_config()
