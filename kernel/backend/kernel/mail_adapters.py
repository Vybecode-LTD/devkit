"""The site's mail adapters: SMTP and Resend (decision 0033).

SMTP comes first: SMTP_HOST set means SMTP, and Resend is only for a host
that blocks SMTP, where RESEND_API_KEY is set without SMTP_HOST
(`KernelConfig.mail_adapter`, the owner's rule). `create_app` puts it behind
`kernel.email.Checked`. Each is a `kernel.email.Mailer`: it delivers one
message or raises `MailError`, which says whether trying again can help, and
never holds the address, the subject, the body or a credential. Neither logs
anything of a message.

- `SmtpMailer`, lifted from VybeSite `services/email_service.py`: the standard
  library's `smtplib` in `asyncio.to_thread`, implicit TLS on port 465 and
  STARTTLS on any other, with certificates checked, and a 15-second timeout.
  The first choice wherever the host allows outbound SMTP.
- `ResendMailer`, only where the host blocks SMTP (Railway's Hobby plan):
  from Basefra.me `app/mail.py`, made to raise rather than swallow: Resend's `POST /emails` over httpx, with a 10-second timeout.
  400, 401, 403, 409 and 422 aren't retryable; 429 and 5xx are, as Resend's
  docs say.
- `from_header`, from VybeSite `senders/base.py`: the From header built by the
  standard library, so a quote or comma in the name can't add an address,
  with an international domain in IDNA.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

import httpx

from kernel.config import KernelConfig, mail_problems
from kernel.email import LogMailer, Mailer, MailError

log = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 15
RESEND_TIMEOUT_SECONDS = 10
RESEND_ENDPOINT = "https://api.resend.com/emails"


def header_address(address: str) -> str:
    """The address as a header can carry it: ASCII, with an international
    domain in IDNA. A local part beyond ASCII needs SMTPUTF8 end to end,
    which these adapters don't negotiate, so it is refused (ValueError)."""
    address = address.strip()
    if address.isascii():
        return address
    local, at, domain = address.rpartition("@")
    if at and local.isascii():
        try:
            return f"{local}@{domain.encode('idna').decode('ascii')}"
        except UnicodeError:
            pass
    raise ValueError(
        "The address has characters beyond ASCII before the @, which a mail header can't carry here."
    )


def from_header(name: str, address: str) -> str:
    """`Name <address>`, quoted and escaped by the standard library, with
    line breaks in the name folded to spaces."""
    return formataddr((" ".join(name.split()), header_address(address)))


def _recipient(to: str) -> str:
    try:
        return header_address(to)
    except ValueError as error:
        raise MailError(f"{error} The message wasn't sent.", retryable=False) from None


@dataclass(frozen=True)
class SmtpMailer:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    from_header: str

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        message = EmailMessage()
        message["From"] = self.from_header
        message["To"] = _recipient(to)
        message["Subject"] = subject
        message["Date"] = formatdate(usegmt=True)
        message["Message-ID"] = make_msgid(domain=parseaddr(self.from_header)[1].rpartition("@")[2])
        message.set_content(text)
        if html is not None:
            message.add_alternative(html, subtype="html")
        try:
            await asyncio.to_thread(self._deliver, message)
        except smtplib.SMTPRecipientsRefused as refused:
            codes = [code for code, _ in refused.recipients.values()]
            code = codes[0] if codes else 550
            raise MailError(
                f"The SMTP server refused the recipient ({code}).", retryable=400 <= code < 500
            ) from None
        except smtplib.SMTPResponseException as error:
            raise MailError(
                f"The SMTP server refused the message ({error.smtp_code}).",
                retryable=400 <= error.smtp_code < 500,
            ) from None
        except smtplib.SMTPNotSupportedError:
            raise MailError(
                "The SMTP server doesn't offer STARTTLS, so nothing was sent.", retryable=False
            ) from None
        except (smtplib.SMTPException, OSError) as error:
            raise MailError(
                f"Couldn't reach the SMTP server ({type(error).__name__}).", retryable=True
            ) from None

    def _deliver(self, message: EmailMessage) -> None:
        context = ssl.create_default_context()
        server: smtplib.SMTP
        if self.port == 465:
            server = smtplib.SMTP_SSL(
                self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS, context=context
            )
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS)
        with server:
            if self.port != 465:
                server.starttls(context=context)
            if self.username:
                server.login(self.username, self.password)
            server.send_message(message)


@dataclass(frozen=True)
class ResendMailer:
    api_key: str = field(repr=False)
    from_header: str
    #: Tests hand in httpx.MockTransport; a site leaves it None.
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        payload: dict[str, object] = {
            "from": self.from_header,
            "to": [_recipient(to)],
            "subject": subject,
            "text": text,
        }
        if html is not None:
            payload["html"] = html
        try:
            async with httpx.AsyncClient(
                timeout=RESEND_TIMEOUT_SECONDS, transport=self.transport
            ) as client:
                response = await client.post(
                    RESEND_ENDPOINT,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.TimeoutException:
            raise MailError(
                "Resend didn't answer in time; the message may have gone.", retryable=True
            ) from None
        except httpx.HTTPError as error:
            raise MailError(
                f"Couldn't reach Resend ({type(error).__name__}).", retryable=True
            ) from None
        if response.is_success:
            return
        status = response.status_code
        retryable = status == 429 or status >= 500
        raise MailError(
            f"Resend refused the message ({status} {_error_name(response)}).",
            retryable=retryable,
            retry_after=_seconds(response.headers.get("retry-after")) if status == 429 else None,
        )


def _error_name(response: httpx.Response) -> str:
    """Resend's error name (`validation_error`), never its message, which can
    repeat the address."""
    try:
        name = response.json().get("name")
    except (ValueError, AttributeError):
        return "error"
    return name if isinstance(name, str) and name.replace("_", "").isalnum() else "error"


def _seconds(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def mailer_from_config(config: KernelConfig) -> Mailer:
    """SMTP when SMTP_HOST is set, Resend when only RESEND_API_KEY is, or
    LogMailer when neither is or mail is set in part (outside DEBUG
    `refuse_unsafe` has already stopped the start for that)."""
    if not config.mail_adapter or mail_problems(config):
        return LogMailer()
    if config.mail_adapter == "smtp" and config.resend_api_key.get_secret_value().strip():
        log.warning(
            "RESEND_API_KEY is set but unused: SMTP_HOST is set, and SMTP comes first. "
            "Resend is only for a host that blocks SMTP."
        )
    sender = from_header(
        config.mail_from_name.strip() or config.site_name, config.mail_from.strip()
    )
    if config.mail_adapter == "smtp":
        return SmtpMailer(
            config.smtp_host.strip(),
            config.smtp_port,
            config.smtp_username.strip(),
            config.smtp_password.get_secret_value(),
            sender,
        )
    return ResendMailer(config.resend_api_key.get_secret_value().strip(), sender)
