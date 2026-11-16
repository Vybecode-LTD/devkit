"""The site's mail adapters: SMTP and Resend (decision 0033).

SMTP runs against a fake `smtplib`; Resend against `httpx.MockTransport`.
Neither reaches a network. What each must never do: put the API key, the
password, the address or the body in an error.
"""

from __future__ import annotations

import email as stdlib_email
import json
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, ClassVar

import httpx
import pytest

from kernel import mail_adapters
from kernel.email import LogMailer, MailError
from kernel.mail_adapters import ResendMailer, SmtpMailer, from_header, mailer_from_config

from .conftest import make_config

PASSWORD = "smtp-pass-5d1e09"
API_KEY = "re_test_key_9a7c44"
SECRETS = (PASSWORD, API_KEY, "reader@vibe.test", "the body text")


def _clean(error: BaseException) -> bool:
    return not any(secret in str(error) for secret in SECRETS)


# --- the From header ----------------------------------------------------------------


def test_the_from_header_is_built_safely() -> None:
    assert from_header("Vibe Site", "hello@vibe.test") == "Vibe Site <hello@vibe.test>"
    assert (
        from_header('Evil", <x@evil.test>\r\n', "hello@vibe.test")
        == '"Evil\\", <x@evil.test>" <hello@vibe.test>'
    )
    assert from_header("Vibe", "hello@exämple.test") == "Vibe <hello@xn--exmple-cua.test>"
    with pytest.raises(ValueError, match="ASCII"):
        from_header("Vibe", "hëllo@vibe.test")


# --- SMTP -------------------------------------------------------------------------


class FakeSMTP:
    """Stands in for smtplib.SMTP and SMTP_SSL, recording what was asked."""

    calls: ClassVar[list[tuple[str, Any]]] = []
    fail_on: ClassVar[str] = ""
    error: ClassVar[BaseException | None] = None

    def __init__(
        self, host: str, port: int, *, timeout: float, context: ssl.SSLContext | None = None
    ) -> None:
        FakeSMTP.calls.append(
            ("connect", (type(self).__name__, host, port, timeout, context is not None))
        )
        self._step("connect")

    def _step(self, name: str) -> None:
        if FakeSMTP.fail_on == name and FakeSMTP.error is not None:
            raise FakeSMTP.error

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *_: object) -> None:
        FakeSMTP.calls.append(("quit", None))

    def starttls(self, *, context: ssl.SSLContext) -> None:
        FakeSMTP.calls.append(("starttls", context.verify_mode == ssl.CERT_REQUIRED))
        self._step("starttls")

    def login(self, user: str, password: str) -> None:
        FakeSMTP.calls.append(("login", (user, password == PASSWORD)))
        self._step("login")

    def send_message(self, message: EmailMessage) -> None:
        FakeSMTP.calls.append(("send", message))
        self._step("send")


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> type[FakeSMTP]:
    FakeSMTP.calls = []
    FakeSMTP.fail_on = ""
    FakeSMTP.error = None
    monkeypatch.setattr(mail_adapters.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mail_adapters.smtplib, "SMTP_SSL", FakeSMTPSSL)
    return FakeSMTP


def smtp(port: int = 587, username: str = "postmaster") -> SmtpMailer:
    return SmtpMailer("smtp.vibe.test", port, username, PASSWORD, "Vibe Site <hello@vibe.test>")


async def test_smtp_on_587_starts_tls_logs_in_and_sends(fake_smtp: type[FakeSMTP]) -> None:
    await smtp().send("reader@vibe.test", "Hello", "the body text", "<p>hi</p>")
    names = [name for name, _ in fake_smtp.calls]
    assert names == ["connect", "starttls", "login", "send", "quit"]
    assert fake_smtp.calls[0][1] == ("FakeSMTP", "smtp.vibe.test", 587, 15, False)
    assert fake_smtp.calls[1][1] is True  # certificates checked
    assert fake_smtp.calls[2][1] == ("postmaster", True)
    message = fake_smtp.calls[3][1]
    assert message["From"] == "Vibe Site <hello@vibe.test>"
    assert message["To"] == "reader@vibe.test"
    assert message["Subject"] == "Hello"
    assert message["Message-ID"].endswith("@vibe.test>")
    assert message["Date"]
    parsed = stdlib_email.message_from_bytes(message.as_bytes())
    parts = [part.get_content_type() for part in parsed.walk()]
    assert parts == ["multipart/alternative", "text/plain", "text/html"]


async def test_smtp_on_465_is_tls_from_the_start(fake_smtp: type[FakeSMTP]) -> None:
    await smtp(port=465).send("reader@vibe.test", "Hello", "the body text")
    assert fake_smtp.calls[0][1] == ("FakeSMTPSSL", "smtp.vibe.test", 465, 15, True)
    assert [name for name, _ in fake_smtp.calls] == ["connect", "login", "send", "quit"]
    assert fake_smtp.calls[2][1].get_content_type() == "text/plain"


async def test_smtp_without_a_username_skips_login(fake_smtp: type[FakeSMTP]) -> None:
    await smtp(username="").send("reader@vibe.test", "Hello", "the body text")
    assert "login" not in [name for name, _ in fake_smtp.calls]


async def test_smtp_sends_to_an_international_domain(fake_smtp: type[FakeSMTP]) -> None:
    await smtp().send("reader@exämple.test", "Hello", "the body text")
    assert fake_smtp.calls[3][1]["To"] == "reader@xn--exmple-cua.test"


async def test_smtp_refuses_an_address_it_cannot_carry(fake_smtp: type[FakeSMTP]) -> None:
    with pytest.raises(MailError) as caught:
        await smtp().send("rëader@vibe.test", "Hello", "the body text")
    assert caught.value.retryable is False
    assert fake_smtp.calls == []


@pytest.mark.parametrize(
    ("step", "error", "retryable"),
    [
        ("login", smtplib.SMTPAuthenticationError(535, b"bad credentials"), False),
        (
            "send",
            smtplib.SMTPRecipientsRefused({"reader@vibe.test": (550, b"no such user")}),
            False,
        ),
        ("send", smtplib.SMTPRecipientsRefused({"reader@vibe.test": (451, b"try later")}), True),
        ("send", smtplib.SMTPSenderRefused(553, b"not yours", "hello@vibe.test"), False),
        ("send", smtplib.SMTPDataError(452, b"mailbox full for now"), True),
        ("send", smtplib.SMTPServerDisconnected("gone"), True),
        ("starttls", smtplib.SMTPNotSupportedError("no STARTTLS"), False),
        ("connect", ConnectionRefusedError("refused"), True),
        ("connect", TimeoutError("slow"), True),
    ],
)
async def test_smtp_failures_say_whether_to_try_again(
    fake_smtp: type[FakeSMTP], step: str, error: BaseException, retryable: bool
) -> None:
    fake_smtp.fail_on = step
    fake_smtp.error = error
    with pytest.raises(MailError) as caught:
        await smtp().send("reader@vibe.test", "Hello", "the body text")
    assert caught.value.retryable is retryable
    assert _clean(caught.value)


def test_the_smtp_password_is_not_in_its_repr() -> None:
    assert PASSWORD not in repr(smtp())


# --- Resend -----------------------------------------------------------------------


def resend(handler: Any) -> ResendMailer:
    return ResendMailer(
        API_KEY, "Vibe Site <hello@vibe.test>", transport=httpx.MockTransport(handler)
    )


async def test_resend_posts_the_message_with_its_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "4ef9a417"})

    await resend(handler).send("reader@exämple.test", "Hello", "the body text", "<p>hi</p>")
    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert json.loads(request.content) == {
        "from": "Vibe Site <hello@vibe.test>",
        "to": ["reader@xn--exmple-cua.test"],
        "subject": "Hello",
        "text": "the body text",
        "html": "<p>hi</p>",
    }


async def test_resend_leaves_out_html_when_there_is_none() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "x"})

    await resend(handler).send("reader@vibe.test", "Hello", "the body text")
    assert "html" not in bodies[0]


@pytest.mark.parametrize(
    ("status", "headers", "retryable", "retry_after"),
    [
        (400, {}, False, None),
        (401, {}, False, None),
        (403, {}, False, None),
        (409, {}, False, None),
        (422, {}, False, None),
        (429, {"retry-after": "2"}, True, 2.0),
        (429, {"retry-after": "soon"}, True, None),
        (500, {}, True, None),
        (503, {}, True, None),
    ],
)
async def test_resend_failures_say_whether_to_try_again(
    status: int, headers: dict[str, str], retryable: bool, retry_after: float | None
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        body = {
            "statusCode": status,
            "name": "validation_error",
            "message": "reader@vibe.test is bad: the body text",
        }
        return httpx.Response(status, json=body, headers=headers)

    with pytest.raises(MailError) as caught:
        await resend(handler).send("reader@vibe.test", "Hello", "the body text")
    assert caught.value.retryable is retryable
    assert caught.value.retry_after == retry_after
    assert str(status) in str(caught.value)
    assert _clean(caught.value)


async def test_resend_names_its_error_but_not_its_message() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"name": "validation_error", "message": "reader@vibe.test"})

    with pytest.raises(MailError, match="validation_error") as caught:
        await resend(handler).send("reader@vibe.test", "Hello", "the body text")
    assert _clean(caught.value)


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.ConnectTimeout("slow")],
)
async def test_resend_unreachable_or_silent_is_retryable(error: httpx.HTTPError) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise error

    with pytest.raises(MailError) as caught:
        await resend(handler).send("reader@vibe.test", "Hello", "the body text")
    assert caught.value.retryable is True
    assert _clean(caught.value)


def test_the_resend_key_is_not_in_its_repr() -> None:
    assert API_KEY not in repr(resend(lambda _: httpx.Response(200)))


# --- choosing the adapter -----------------------------------------------------------


def test_the_config_picks_the_adapter() -> None:
    assert isinstance(mailer_from_config(make_config()), LogMailer)
    chosen = mailer_from_config(
        make_config(
            mail_from="hello@vibe.test",
            smtp_host="smtp.vibe.test",
            site_name="Vibe",
        )
    )
    assert isinstance(chosen, SmtpMailer)
    assert chosen.port == 587
    assert chosen.from_header == "Vibe <hello@vibe.test>"
    named = mailer_from_config(
        make_config(
            mail_from="hello@vibe.test",
            mail_from_name="Vibe Mail",
            resend_api_key=API_KEY,
        )
    )
    assert isinstance(named, ResendMailer)
    assert named.from_header == "Vibe Mail <hello@vibe.test>"


def test_smtp_wins_when_both_are_set_and_says_resend_is_unused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING", logger="kernel.mail_adapters"):
        both = mailer_from_config(
            make_config(
                mail_from="hello@vibe.test", smtp_host="smtp.vibe.test", resend_api_key=API_KEY
            )
        )
    assert isinstance(both, SmtpMailer)
    [record] = caplog.records
    assert "RESEND_API_KEY is set but unused" in record.getMessage()
    assert API_KEY not in record.getMessage()


def test_an_adapter_set_in_part_falls_back_to_the_log_with_debug() -> None:
    # Outside DEBUG refuse_unsafe has already stopped the start; with DEBUG on
    # it only logged, so mail goes nowhere rather than half-configured.
    assert isinstance(
        mailer_from_config(make_config(debug=True, smtp_host="smtp.vibe.test")), LogMailer
    )
    assert isinstance(
        mailer_from_config(make_config(debug=True, resend_api_key=API_KEY)), LogMailer
    )


def test_create_app_uses_the_configured_adapter() -> None:
    from kernel.app import create_app
    from kernel.email import Checked

    app = create_app(config=make_config(mail_from="hello@vibe.test", resend_api_key=API_KEY))
    assert isinstance(app.state.mailer, Checked)
    assert isinstance(app.state.mailer.inner, ResendMailer)


async def test_an_international_domain_too_long_for_dns_is_refused(
    fake_smtp: type[FakeSMTP],
) -> None:
    with pytest.raises(MailError, match="ASCII") as caught:
        await smtp().send("reader@" + "ä" * 70 + ".test", "Hello", "the body text")
    assert caught.value.retryable is False
    assert fake_smtp.calls == []


async def test_a_resend_error_without_json_is_named_plainly() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>Bad gateway</html>")

    with pytest.raises(MailError, match=r"\(502 error\)") as caught:
        await resend(handler).send("reader@vibe.test", "Hello", "the body text")
    assert caught.value.retryable is True
