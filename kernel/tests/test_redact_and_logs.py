"""Nothing private reaches a log line or the error tracker."""

from __future__ import annotations

import json
import logging

import pytest

from kernel import logs
from kernel.config import KernelConfig
from kernel.error_tracking import init, scrub, scrub_breadcrumb
from kernel.redact import ADDRESS, MAX_TEXT, REDACTED, clean, clean_text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail ana@site.test now", f"mail {ADDRESS} now"),
        ("GET /api/x?token=abc HTTP/1.1", f"GET /api/x?{REDACTED} HTTP/1.1"),
        ("from 203.0.113.9:443 and 2001:db8::1", f"from {REDACTED} and {REDACTED}"),
        ("at 12:30:45", "at 12:30:45"),
        ("postgres://user:pw@db:5432/x", f"postgres://{REDACTED}@db:5432/x"),
        ("tok " + "A1b2" * 10, f"tok {REDACTED}"),
        ("id 0b4f6a52-6a1e-4d8b-9f0e-2a1b3c4d5e6f", "id 0b4f6a52-6a1e-4d8b-9f0e-2a1b3c4d5e6f"),
        (
            "the_long_snake_case_name_of_a_setting_here",
            "the_long_snake_case_name_of_a_setting_here",
        ),
        (
            "DETAIL:  Key (email)=(ana@site.test) already exists.",
            f"DETAIL:  Key (email)=({REDACTED}) already exists.",
        ),
        ("[parameters: ('ana', 'pw')]", "[parameters: hidden]"),
        ("Failing row contains (1, ana, x).", f"Failing row contains ({REDACTED})."),
    ],
)
def test_clean_text(text: str, expected: str) -> None:
    assert clean_text(text) == expected


def test_long_text_is_cut_first() -> None:
    assert len(clean_text("x " * MAX_TEXT)) <= MAX_TEXT


def test_clean_walks_values() -> None:
    assert clean({"ana@site.test": ["a@b.test", 3, ("x",)]}) == {ADDRESS: [ADDRESS, 3, ["x"]]}


def _record(message: str, level: int = logging.INFO, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("kernel.test", level, __file__, 1, message, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_lines() -> None:
    line = json.loads(
        logs.JsonFormatter().format(_record("signed in ana@site.test", feature="blog"))
    )
    assert line["message"] == f"signed in {ADDRESS}"
    assert (line["level"], line["logger"], line["feature"]) == ("INFO", "kernel.test", "blog")


def test_json_tracebacks_are_cleaned() -> None:
    try:
        raise ValueError("bad ana@site.test")
    except ValueError:
        import sys

        record = _record("failed")
        record.exc_info = sys.exc_info()
    line = json.loads(logs.JsonFormatter().format(record))
    assert line["error"] == "ValueError"
    assert "ana@site.test" not in line["traceback"]


def test_text_lines_are_cleaned() -> None:
    assert logs.TextFormatter().format(_record("to ana@site.test")).endswith(f"to {ADDRESS}")


def test_streams_split(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    before = list(root.handlers), root.level
    try:
        logs.configure("text", "INFO")
        logs.configure("text", "INFO")  # again: replaced, not doubled
        logging.getLogger("kernel.test").info("routine")
        logging.getLogger("kernel.test").warning("serious")
        out, err = capsys.readouterr()
        assert out.count("routine") == 1
        assert "serious" not in out
        assert err.count("serious") == 1
        assert "routine" not in err
        assert logging.getLogger("uvicorn.access").level == logging.WARNING
    finally:
        for handler in list(root.handlers):
            if handler not in before[0]:
                root.removeHandler(handler)
        root.setLevel(before[1])


def test_no_dsn_no_tracking() -> None:
    assert init(KernelConfig(sentry_dsn=""), "web") is False


def test_a_bad_dsn_is_logged_by_kind(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger="kernel.error_tracking"):
        assert init(KernelConfig(sentry_dsn="not a dsn secretvalue"), "web") is False
    assert "can't be used (" in caplog.text
    assert "secretvalue" not in caplog.text


def test_scrub_removes_the_private_parts() -> None:
    event = {
        "event_id": "a" * 32,
        "user": {"ip_address": "203.0.113.9"},
        "request": {
            "url": "https://devkit.test/api/x?token=abc",
            "data": {"password": "pw"},
            "cookies": {"__Host-dk_session": "s"},
            "query_string": "token=abc",
            "headers": {"User-Agent": "UA", "Authorization": "Bearer t", "Cookie": "c"},
        },
        "contexts": {"trace": {"trace_id": "b" * 32, "op": "http"}},
        "message": "failed for ana@site.test",
    }
    cleaned = scrub(event)
    assert cleaned["event_id"] == "a" * 32
    assert cleaned["contexts"]["trace"]["trace_id"] == "b" * 32
    assert "user" not in cleaned
    assert cleaned["request"] == {
        "url": "https://devkit.test/api/x",
        "headers": {"User-Agent": "UA"},
    }
    assert cleaned["message"] == f"failed for {ADDRESS}"


def test_scrub_breadcrumb() -> None:
    crumb = scrub_breadcrumb({"message": "to a@b.test", "data": {"http.query": "q=1", "url": "/x"}})
    assert crumb == {"message": f"to {ADDRESS}", "data": {"http.query": REDACTED, "url": "/x"}}
