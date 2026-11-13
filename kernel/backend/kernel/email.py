"""Mail out of the kernel (SPEC.md sections 6 and 14; decision 0013).

A site's mail goes through one adapter, a `Mailer`: SMTP, Mailgun or Resend,
chosen in K3, when `email.send(template, to, context)` arrives on top of it.
Until then K2's sign-up, codes and resets reach the mailer through
`get_mailer`.

- `Mailer`: `async send(to, subject, text, html=None)`. An adapter delivers or
  raises, and never logs the address, the subject or the body.
- `Checked`: what `create_app` puts in front of the site's adapter, so every
  adapter gets one recipient, no line break in the address or the subject
  (header injection), and bounded sizes. A message that fails the checks is
  the caller's bug: ValueError, naming the field, never its value.
- `LogMailer`, the default until a site sets an adapter: sends nothing, and
  logs a warning that holds nothing of the message, so a missing adapter
  shows in the logs without anyone's address, codes or links in them.
- `CapturingMailer`: keeps each message in memory for the harness's
  `/api/_test/mail`. Never in a site: whoever reads it can sign in as anyone.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

log = logging.getLogger(__name__)

#: RFC 5321's limit on a forward path, less its angle brackets.
MAX_ADDRESS = 254
MAX_SUBJECT = 255
MAX_BODY = 256 * 1024
#: One address, bare: no display name, quotes, comments, list separators or
#: whitespace, and exactly one @. Letters beyond ASCII are allowed (RFC 6531).
_ADDRESS = re.compile(r"[^@\s,;:<>()\[\]\"\\]+@[^@\s,;:<>()\[\]\"\\]+")
#: Control characters (CR, LF, tab, NUL, NEL…) and Unicode's line and paragraph
#: separators: any of them in a header can start a new one.
_BREAKS = {"Cc", "Zl", "Zp"}


class Mailer(Protocol):
    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None: ...


def _has_break(value: str) -> bool:
    return any(unicodedata.category(character) in _BREAKS for character in value)


def check(to: str, subject: str, text: str, html: str | None = None) -> None:
    """Raises ValueError, naming the field, unless the message is safe to hand
    to any adapter."""
    if len(to) > MAX_ADDRESS or _has_break(to) or not _ADDRESS.fullmatch(to):
        raise ValueError("A message's `to` must be one bare email address.")
    if not subject.strip() or len(subject) > MAX_SUBJECT or _has_break(subject):
        raise ValueError(f"A message's subject must be one line of 1 to {MAX_SUBJECT} characters.")
    _check_body("text", text)
    if html is not None:
        _check_body("html", html)


def _check_body(field: str, body: str) -> None:
    if not body.strip() or len(body) > MAX_BODY or "\x00" in body:
        raise ValueError(f"A message's {field} must hold 1 to {MAX_BODY} characters and no NUL.")


class Checked:
    """The site's adapter behind `check`: the mailer `create_app` installs."""

    def __init__(self, inner: Mailer) -> None:
        self.inner = inner

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        check(to, subject, text, html)
        await self.inner.send(to, subject, text, html)


class LogMailer:
    """Sends nothing: the default until a site sets its adapter."""

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        log.warning("A message was dropped: no mail adapter is set, so the site sends no mail.")


@dataclass(frozen=True)
class Captured:
    to: str
    subject: str
    text: str
    html: str | None


class CapturingMailer:
    """Keeps the newest `keep` messages, for the harness's test support only."""

    def __init__(self, keep: int = 1000) -> None:
        self._messages: deque[Captured] = deque(maxlen=keep)

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        self._messages.append(Captured(to, subject, text, html))

    def to(self, address: str) -> list[Captured]:
        """The messages to `address`, oldest first. Addresses match lowercased,
        as accounts are looked up (`auth_user.email_normal`)."""
        wanted = address.lower()
        return [message for message in self._messages if message.to.lower() == wanted]

    def clear(self) -> None:
        self._messages.clear()


def get_mailer(request: Request) -> Mailer:
    """The app's mailer, as a dependency: `mailer: Mailer = Depends(get_mailer)`."""
    mailer: Mailer = request.app.state.mailer
    return mailer
