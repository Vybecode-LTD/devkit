"""Mail out of the kernel (SPEC.md sections 6 and 14; decisions 0013 and 0033).

`send(template, to, context)` is how a module, the kernel or a job sends mail:

- **Templates.** A `Template` holds a subject, a text body and an optional
  HTML body in `string.Template` syntax (`$name`, `${name}`; `$$` for a dollar
  sign). A module declares its own, named `<module id>.<name>`, on
  `InstalledModule(emails=...)`; a site rewords any of them through
  `create_app(emails=...)`, using only the placeholders the original uses.
  `create_app` checks both and refuses to start on a bad one.
- **Rendering.** Every template also gets `site_name` and `site_url`. In the
  subject, each value is folded onto one line; in the HTML, each is
  HTML-escaped; the text body takes them as they are. A missing value is
  ValueError naming the template and the placeholder, never a value.
- **The adapter** is the site's `Mailer` (`kernel.mail_adapters`: SMTP
  first, Resend only on a host that blocks SMTP), behind `Checked`. `create_app` installs it and the
  templates for `send`; a worker calls `install` itself. A failed delivery is
  `MailError`, which says whether trying again can help.
- **Queueing** (decision 0035). `queue(db, template, to, context)` renders now
  and adds a `kernel.send_mail` job to the caller's transaction, sealed
  (`kernel.jobs`): the mail goes out only if the change commits, and a
  provider's hiccup is retried (`MailError.retryable`, after `retry_after`),
  while a refusal ends it. The kernel's own mails go this way; `send` stays
  for a job or a script that sends now.

- `Mailer`: `async send(to, subject, text, html=None, headers=None)`. An
  adapter delivers or raises, and never logs the address, the subject or the
  body. `headers` are only the one-click unsubscribe pair a notice email
  carries (`HEADERS`, RFC 8058; kernel.notifications).
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

import html as html_escape
import logging
import re
import string
import unicodedata
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from kernel import jobs

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


#: The only headers a message may add: one-click unsubscribe (RFC 8058).
HEADERS = frozenset({"List-Unsubscribe", "List-Unsubscribe-Post"})
MAX_HEADER = 1000


class Mailer(Protocol):
    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None: ...


def _has_break(value: str) -> bool:
    return any(unicodedata.category(character) in _BREAKS for character in value)


def is_address(text: str) -> bool:
    """Whether `text` is one bare address a message can go to: what a form
    taking an address (sign-up) accepts, so mail to it can't fail `check`."""
    return len(text) <= MAX_ADDRESS and not _has_break(text) and bool(_ADDRESS.fullmatch(text))


def check(
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> None:
    """Raises ValueError, naming the field, unless the message is safe to hand
    to any adapter."""
    if not is_address(to):
        raise ValueError("A message's `to` must be one bare email address.")
    if not subject.strip() or len(subject) > MAX_SUBJECT or _has_break(subject):
        raise ValueError(f"A message's subject must be one line of 1 to {MAX_SUBJECT} characters.")
    _check_body("text", text)
    if html is not None:
        _check_body("html", html)
    for name, value in (headers or {}).items():
        if name not in HEADERS:
            raise ValueError(f"A message may add only the header(s) {sorted(HEADERS)}.")
        if not value.strip() or len(value) > MAX_HEADER or _has_break(value):
            raise ValueError(f"A message's {name} header must be one line of 1 to {MAX_HEADER}.")


def _check_body(field: str, body: str) -> None:
    if not body.strip() or len(body) > MAX_BODY or "\x00" in body:
        raise ValueError(f"A message's {field} must hold 1 to {MAX_BODY} characters and no NUL.")


class Checked:
    """The site's adapter behind `check`: the mailer `create_app` installs."""

    def __init__(self, inner: Mailer) -> None:
        self.inner = inner

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        check(to, subject, text, html, headers)
        if headers:
            await self.inner.send(to, subject, text, html, headers)
        else:
            await self.inner.send(to, subject, text, html)


class LogMailer:
    """Sends nothing: the default until a site sets its adapter."""

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        log.warning("A message was dropped: no mail adapter is set, so the site sends no mail.")


@dataclass(frozen=True)
class Captured:
    to: str
    subject: str
    text: str
    html: str | None
    headers: Mapping[str, str] | None = None


class CapturingMailer:
    """Keeps the newest `keep` messages, for the harness's test support only."""

    def __init__(self, keep: int = 1000) -> None:
        self._messages: deque[Captured] = deque(maxlen=keep)

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._messages.append(Captured(to, subject, text, html, dict(headers or {}) or None))

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


# --- templates and send (decision 0033) ------------------------------------------

#: A template's name: the owning module's id (or `kernel`), a dot, and a name.
_TEMPLATE_NAME = re.compile(r"([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\.([a-z0-9_]+)")
#: What every template gets without being passed it.
SITE_VALUES = frozenset({"site_name", "site_url"})


class MailError(RuntimeError):
    """A message that wasn't delivered, or may not have been. `retryable` says
    whether trying again can help (a limit, a provider's 5xx, a dropped
    connection) or not (a bad key, an unverified domain, a refused address);
    `retry_after` is the provider's wait in seconds, when it gave one. The
    message never holds the address, the subject, the body or a credential."""

    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


@dataclass(frozen=True)
class Template:
    subject: str
    text: str
    html: str | None = None


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str | None


def _placeholders(name: str, template: Template) -> frozenset[str]:
    """The template's placeholders; ValueError, naming it, if it can't render
    or if its fixed wording could never pass `check` (a blank or oversized
    subject or body, a NUL)."""
    subject = template.subject
    if not subject.strip() or len(subject) > MAX_SUBJECT or any(map(_has_break, subject)):
        raise ValueError(
            f"Email template {name}'s subject must be one line of 1 to {MAX_SUBJECT} characters."
        )
    for field, body in (("text", template.text), ("html", template.html)):
        if body is not None and (not body.strip() or len(body) > MAX_BODY or chr(0) in body):
            raise ValueError(
                f"Email template {name}'s {field} must hold 1 to {MAX_BODY} characters and no NUL."
            )
    found: set[str] = set()
    for part in (template.subject, template.text, template.html):
        if part is None:
            continue
        compiled = string.Template(part)
        if not compiled.is_valid():
            raise ValueError(
                f"Email template {name} has a $ that starts no placeholder: write $$ for a dollar sign."
            )
        found.update(compiled.get_identifiers())
    return frozenset(found)


def build_templates(
    declared: Iterable[tuple[str, Mapping[str, Template]]], site: Mapping[str, Template]
) -> dict[str, Template]:
    """Every template, from (module id, its templates) pairs and the site's
    rewording. Raises ValueError, naming the template, on any it can't take."""
    templates: dict[str, Template] = {}
    placeholders: dict[str, frozenset[str]] = {}
    for owner, emails in declared:
        for name, template in emails.items():
            match = _TEMPLATE_NAME.fullmatch(name)
            if match is None or match.group(1) != owner:
                raise ValueError(
                    f"{owner} may only declare {owner}.* email templates named in [a-z0-9_], not {name}."
                )
            placeholders[name] = _placeholders(name, template)
            templates[name] = template
    for name, template in site.items():
        if name not in templates:
            raise ValueError(f"The site rewords email template {name}, which no module declares.")
        extra = _placeholders(name, template) - placeholders[name] - SITE_VALUES
        if extra:
            listed = ", ".join(f"${placeholder}" for placeholder in sorted(extra))
            raise ValueError(f"The site's {name} uses {listed}, which its senders don't pass.")
        templates[name] = template
    return templates


@dataclass(frozen=True)
class _Postbox:
    mailer: Mailer
    templates: Mapping[str, Template]
    site_name: str
    site_url: str


_postbox: _Postbox | None = None


def install(
    mailer: Mailer, templates: Mapping[str, Template], *, site_name: str, site_url: str
) -> None:
    """Sets the mailer and the templates `send` uses: `create_app` calls it,
    and so does a worker that sends mail outside a request. Any mailer goes
    behind `Checked`, once, so a worker's mail gets the same checks."""
    global _postbox
    checked = mailer if isinstance(mailer, Checked) else Checked(mailer)
    _postbox = _Postbox(checked, dict(templates), site_name, site_url.rstrip("/"))


def site_url() -> str:
    """SITE_URL as `install` was given it, without a trailing slash."""
    return _current().site_url


def _current() -> _Postbox:
    if _postbox is None:
        raise RuntimeError(
            "Mail isn't set up: create_app installs the mailer and templates (a worker calls install)."
        )
    return _postbox


def _one_line(value: str) -> str:
    return " ".join(
        "".join(" " if _has_break(character) else character for character in value).split()
    )


def render(template: str, context: Mapping[str, str | int]) -> Rendered:
    """The message `template` makes with `context`."""
    postbox = _current()
    chosen = postbox.templates.get(template)
    if chosen is None:
        raise ValueError(
            f"No email template {template}: a module declares it on InstalledModule(emails=...)."
        )
    for key in SITE_VALUES & set(context):
        raise ValueError(f"An email's context can't set {key}: the kernel fills it in.")
    values = {key: str(value) for key, value in context.items()}
    values.update(site_name=postbox.site_name, site_url=postbox.site_url)
    try:
        subject = string.Template(chosen.subject).substitute(
            {k: _one_line(v) for k, v in values.items()}
        )
        text = string.Template(chosen.text).substitute(values)
        html = (
            None
            if chosen.html is None
            else string.Template(chosen.html).substitute(
                {k: html_escape.escape(v) for k, v in values.items()}
            )
        )
    except KeyError as missing:
        raise ValueError(f"Email template {template} needs ${missing.args[0]}.") from None
    return Rendered(subject, text, html)


async def send(template: str, to: str, context: Mapping[str, str | int]) -> None:
    """Renders `template` with `context` and sends it to `to` through the
    site's mailer. Raises ValueError on the caller's bug (an unknown template, a
    missing value, a bad address) and MailError when delivery fails."""
    rendered = render(template, context)
    await _current().mailer.send(to, rendered.subject, rendered.text, rendered.html)


#: A queued mail's payload: any message within `check`'s bounds, as JSON.
#: `check` counts characters; a character takes at most 6 bytes once encoded
#: (4 in UTF-8, 6 for a control character JSON escapes as \u00XX), so a
#: message `send` would take is never refused here (Codex on #63).
_QUEUED_MAIL_LIMIT = 6 * (MAX_ADDRESS + MAX_SUBJECT + 2 * MAX_BODY) + 1024


async def queue(db: AsyncSession, template: str, to: str, context: Mapping[str, str | int]) -> None:
    """Renders `template` now and queues it for `to` in the caller's
    transaction, which the caller commits. Raises ValueError on the caller's
    bug, as `send` does, before anything is queued."""
    rendered = render(template, context)
    await queue_message(db, to, rendered.subject, rendered.text, rendered.html)


async def queue_message(
    db: AsyncSession,
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> None:
    """Queues a message already rendered (the kernel's auth mails render
    theirs through `kernel.auth.mails`). Sealed: its links and codes are
    never readable in the jobs table, and are wiped once it's sent."""
    check(to, subject, text, html, headers)
    payload: dict[str, Any] = {"to": to, "subject": subject, "text": text, "html": html}
    if headers:
        payload["headers"] = dict(headers)
    await jobs.enqueue_up_to(
        db,
        SEND_MAIL.name,
        payload,
        run_at=None,
        key=None,
        sealed=True,
        limit=_QUEUED_MAIL_LIMIT,
    )


async def _send_queued(ctx: jobs.Context, payload: dict[str, Any]) -> None:
    mailer: Mailer = ctx._mailer
    try:
        await mailer.send(
            payload["to"],
            payload["subject"],
            payload["text"],
            payload.get("html"),
            payload.get("headers"),
        )
    except MailError as error:
        if error.retryable:
            after = None if error.retry_after is None else max(0.0, error.retry_after)
            raise jobs.Retry(after) from None
        raise jobs.Abandon("The mail provider refused the message.") from None


#: Sends a queued mail through the worker's mailer.
SEND_MAIL = jobs.handler("kernel.send_mail", tries=5, timeout=60)(_send_queued)
