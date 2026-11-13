"""The mail interface (decision 0013): the checks every adapter sits behind,
the default that logs without the mail, and the capture the harness reads."""

from __future__ import annotations

import logging

import httpx
import pytest
from fastapi import Depends, FastAPI

from kernel.app import create_app
from kernel.email import (
    MAX_BODY,
    MAX_SUBJECT,
    CapturingMailer,
    Checked,
    LogMailer,
    Mailer,
    get_mailer,
)

from .conftest import make_config

ADDRESS = "quill.ward@site.test"
#: create_app connects to nothing until its lifespan runs, and these tests run none.
NOWHERE = "postgresql://devkit:devkit@127.0.0.1:1/none"


class Recording:
    """An adapter that keeps what reached it."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, str | None]] = []

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        self.sent.append((to, subject, text, html))


# --- the checks ---------------------------------------------------------------


async def test_a_good_message_reaches_the_adapter_unchanged() -> None:
    inner = Recording()
    await Checked(inner).send(ADDRESS, "Confirm your email", "Open /auth/verify?token=a", "<p>")
    assert inner.sent == [(ADDRESS, "Confirm your email", "Open /auth/verify?token=a", "<p>")]


async def test_the_limits_themselves_pass() -> None:
    inner = Recording()
    local = "a" * (254 - len("@site.test"))
    await Checked(inner).send(
        f"{local}@site.test", "s" * MAX_SUBJECT, "t" * MAX_BODY, "h" * MAX_BODY
    )
    assert len(inner.sent) == 1


async def test_an_international_address_passes() -> None:
    inner = Recording()
    await Checked(inner).send("zoë@bücher.test", "Grüße", "text")
    assert inner.sent[0][0] == "zoë@bücher.test"


@pytest.mark.parametrize(
    ("to", "subject"),
    [
        ("quill.ward@site.test\r\nBcc: eve@evil.test", "Hello"),  # header injection
        ("quill.ward@site.test\nBcc: eve@evil.test", "Hello"),
        ("quill\x00ward@site.test", "Hello"),  # NUL and DEL aren't whitespace
        ("quill\x7fward@site.test", "Hello"),
        (ADDRESS, "Hello\r\nBcc: eve@evil.test"),  # and through the subject
        (ADDRESS, "Hello\nBcc: eve@evil.test"),
        (ADDRESS, "Hello\rBcc: eve@evil.test"),
        (ADDRESS, "Hello\u2028Bcc: eve@evil.test"),  # a Unicode line separator
        (ADDRESS, "Hello\x85Bcc: eve@evil.test"),  # NEL
        (ADDRESS, "Hello\x00"),
        (ADDRESS, "Hello\tthere"),
        ("quill.ward@site.test, eve@evil.test", "Hello"),  # two recipients
        ("quill.ward@site.test;eve@evil.test", "Hello"),
        ("quill.ward@site.test eve@evil.test", "Hello"),
        ("Quill <quill.ward@site.test>", "Hello"),  # a display name
        ('"eve@evil.test"@site.test', "Hello"),
        ("quill.ward.site.test", "Hello"),  # no @
        ("quill@ward@site.test", "Hello"),
        ("@site.test", "Hello"),
        ("quill.ward@", "Hello"),
        ("", "Hello"),
        ("a" * (255 - len("@site.test")) + "@site.test", "Hello"),  # past 254 characters
        (ADDRESS, ""),  # no subject
        (ADDRESS, "   "),
        (ADDRESS, "s" * (MAX_SUBJECT + 1)),
    ],
)
async def test_a_bad_address_or_subject_never_reaches_the_adapter(to: str, subject: str) -> None:
    inner = Recording()
    with pytest.raises(ValueError, match=r"`to`|subject") as refused:
        await Checked(inner).send(to, subject, "text")
    assert inner.sent == []
    # The error names the field, never the value: it may end up in a log.
    assert "evil" not in str(refused.value)
    assert "quill" not in str(refused.value)


@pytest.mark.parametrize(
    ("text", "html"),
    [
        ("", None),
        ("  \n ", None),
        ("t" * (MAX_BODY + 1), None),
        ("a\x00b", None),
        ("text", "h" * (MAX_BODY + 1)),
        ("text", "a\x00b"),
        ("text", ""),
    ],
)
async def test_a_bad_body_never_reaches_the_adapter(text: str, html: str | None) -> None:
    inner = Recording()
    with pytest.raises(ValueError, match="must hold"):
        await Checked(inner).send(ADDRESS, "Hello", text, html)
    assert inner.sent == []


# --- the default -----------------------------------------------------------------


async def test_the_default_sends_nothing_and_logs_nothing_of_the_mail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="kernel.email")
    await LogMailer().send(
        ADDRESS,
        "482913 is your sign-in code",
        "Your code is 482913, or open /auth/link?token=SECRETTOKEN",
        "<b>482913</b>",
    )
    records = [record for record in caplog.records if record.name == "kernel.email"]
    assert [record.levelno for record in records] == [logging.WARNING]
    shown = records[0].getMessage() + repr(vars(records[0]))
    for private in ("quill", "site.test", "482913", "SECRETTOKEN", "sign-in code"):
        assert private not in shown, private
    assert "no mail adapter" in records[0].getMessage()


# --- the capture ---------------------------------------------------------------


async def test_the_capture_keeps_mail_by_address_oldest_first() -> None:
    capture = CapturingMailer()
    await capture.send("Quill.Ward@Site.test", "one", "first", "<p>first</p>")
    await capture.send("bob@site.test", "two", "someone else's")
    await capture.send(ADDRESS, "three", "second")
    kept = capture.to("QUILL.WARD@site.test")
    assert [(message.subject, message.text) for message in kept] == [
        ("one", "first"),
        ("three", "second"),
    ]
    assert kept[0].to == "Quill.Ward@Site.test"  # as sent
    assert kept[0].html == "<p>first</p>"
    capture.clear()
    assert capture.to(ADDRESS) == []
    assert capture.to("bob@site.test") == []


async def test_the_capture_keeps_only_the_newest() -> None:
    capture = CapturingMailer(keep=2)
    for n in range(3):
        await capture.send(ADDRESS, f"subject {n}", f"text {n}")
    assert [message.text for message in capture.to(ADDRESS)] == ["text 1", "text 2"]


# --- the app ---------------------------------------------------------------------


def test_the_app_mails_through_the_checks_to_the_default() -> None:
    app = create_app(config=make_config(database_url=NOWHERE))
    assert isinstance(app.state.mailer, Checked)
    assert isinstance(app.state.mailer.inner, LogMailer)


async def test_a_sites_mailer_sits_behind_the_checks() -> None:
    inner = Recording()
    app = create_app(config=make_config(database_url=NOWHERE), mailer=inner)
    await app.state.mailer.send(ADDRESS, "Hello", "text")
    with pytest.raises(ValueError, match="subject"):
        await app.state.mailer.send(ADDRESS, "Hello\r\nBcc: eve@evil.test", "text")
    assert inner.sent == [(ADDRESS, "Hello", "text", None)]


async def test_a_route_gets_the_apps_mailer() -> None:
    app = FastAPI()
    capture = CapturingMailer()
    app.state.mailer = Checked(capture)

    @app.post("/send")
    async def send(mailer: Mailer = Depends(get_mailer)) -> dict[str, bool]:
        await mailer.send(ADDRESS, "Hello", "text")
        return {"sent": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://devkit.test") as client:
        assert (await client.post("/send")).status_code == 200
    assert [message.subject for message in capture.to(ADDRESS)] == ["Hello"]
