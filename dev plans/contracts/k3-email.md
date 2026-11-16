---
feature: K3 email (email.send, templates, the site's mail adapter)
status: approved
approved: 2026-11-16 (the owner, with Resend as the API adapter)
plan: dev plans/2026-11-16-next-session-k3-storage.md (section 4, item 4); docs/HANDOFF.md, Next 1
pr: 59
---

# Contract: K3 email (`kernel.email`)

## 1. Goal

A module, the kernel or a job sends mail by template name: `await email.send("blog.comment_reply", to, {"name": ...})`. Each module ships its templates' wording, and a site can reword any of them without touching module code. The site picks its provider with variables: an HTTPS API (which works on Railway's Hobby plan, where outbound SMTP is blocked) or SMTP (any provider, on a host that allows it).

## 2. Interfaces

`kernel/backend/kernel/email.py` (public as `from kernel import email`), extending what K2 built (`Mailer`, `Checked`, `LogMailer`, `CapturingMailer`, `get_mailer`).

```python
@dataclass(frozen=True)
class Template:                     # string.Template syntax: $name or ${name}
    subject: str
    text: str
    html: str | None = None

async def send(template: str, to: str, context: Mapping[str, str | int]) -> None
def render(template: str, context: Mapping[str, str | int]) -> Rendered   # Rendered(subject, text, html)
class MailError(RuntimeError)       # .retryable: bool, .retry_after: float | None; never holds the address or body
```

- **Names:** `<owner>.<name>`, where the owner is the module's id or `kernel`; `<name>` is `[a-z0-9_]+`. A module declares only its own: `InstalledModule(..., emails={"blog.comment_reply": Template(...)})`. A site rewords with `create_app(..., emails={...})`, which may only replace a declared template and may only use placeholders the original uses. Both are checked when the app is built: a wrong name or a stray placeholder stops the start.
- **Rendering:** every template gets `site_name` and `site_url` too. Values are `str()`-ed; in the subject, whitespace runs (line breaks included) become one space; in the HTML, each value is HTML-escaped. A missing placeholder is ValueError naming the template and the placeholder, never a value. Then `Checked` runs as it does now.
- **Sending:** `send` renders, then awaits the site's adapter. A failure raises `MailError` with `retryable` (rate-limited, 5xx, connection lost) set apart from a refusal (bad key, unverified domain, rejected address). Retries arrive with K3's jobs.
- **Which mailer:** `create_app(mailer=...)` as now, else the adapter `MAIL_ADAPTER` names, else `LogMailer`. `create_app` installs the mailer and the templates for `send`; `request.app.state.mailer` stays for K2's routes.
- **Adapters** (`kernel/backend/kernel/mail_adapters.py`): `SmtpMailer` (standard-library `smtplib` in `asyncio.to_thread`; implicit TLS on 465, STARTTLS otherwise, 15 s timeout; from VybeSite `email_service.py`) and `ResendMailer` (Resend's `POST /emails` over `httpx`, 10 s timeout; from Basefra.me `app/mail.py`). The From header is built by `email.utils.formataddr`, with an international domain in IDNA (VybeSite `senders/base.py`).

**Config** (`KernelConfig`): `MAIL_ADAPTER` (blank, `smtp` or `resend`), `MAIL_FROM`, `MAIL_FROM_NAME` (default: `SITE_NAME`), `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_USERNAME`, `SMTP_PASSWORD` (`SecretStr`), and `RESEND_API_KEY` (`SecretStr`). `refuse_unsafe` stops the start outside DEBUG on an adapter whose variables are missing, a `MAIL_FROM` that isn't one address, or a placeholder domain in it.

## 3. Data

None.

## 4. Files

- New: `kernel/backend/kernel/mail_adapters.py`, `kernel/tests/test_email_send.py`, `kernel/tests/test_mail_adapters.py`, `docs/decisions/0033-kernel-email.md`.
- Changed: `kernel/backend/kernel/email.py`, `modules.py` (`emails` on `InstalledModule`), `app.py`, `config.py`, `__init__.py`; `kernel/tests/test_config.py`, `test_email.py`; `.env.example`; `SPEC.md` (2, 6 and the change log); `docs/HANDOFF.md`; `modules/_template` (an example template).

## 5. Conventions this follows

`kernel/backend/kernel/modules.py` (`settings` and `csp` declared on `InstalledModule`, checked by `create_app`), `kernel/backend/kernel/storage.py` (blocking work in `to_thread`; config checks in `config.py`), `kernel/backend/kernel/email.py` (`Checked`: messages that name the field, never its value). The adapters are lifted from VybeSite `services/email_service.py` and `senders/`, and Basefra.me `app/mail.py`; the brand check runs on them.

## 6. Non-goals

- No queue and no retries: mail moves onto K3's jobs next, which use `MailError.retryable`.
- K2's nine auth mails keep their wording in code for now; they move onto `kernel.*` templates in their own PR.
- No HTML layout or branding (K4 themes), no List-Unsubscribe or other extra headers (`notify`), and no bounce or delivery webhooks.
- One HTTPS API adapter, not every provider: another arrives when a site needs it.

## 7. Acceptance

- `kernel/tests/test_email_send.py`: rendering (`site_name` and `site_url`, a subject value with a line break folded, HTML escaped, a missing placeholder named), a module's template, a site's rewording, a site rewording an unknown name or adding a placeholder refused at build, a module declaring another's name refused, `send` reaching the installed mailer, and `Checked` still guarding.
- `kernel/tests/test_mail_adapters.py`: SMTP, with `smtplib` faked (465 is implicit TLS and 587 STARTTLS, login, the From header, a refusal against a dropped connection); Resend, with `httpx.MockTransport` (its request shape and auth, 401/403/422 not retryable, 429 with Retry-After, 5xx and a timeout retryable, and no key in any message).
- `kernel/tests/test_config.py`: each mail problem, by name, never by value.
- The suite stays green, coverage stays at 95% or more, and the new files are at 100%.

## 8. Open questions

None. The owner approved the goal and non-goals and chose Resend on 2026-11-16.

## Changes after approval

- 2026-11-16: a module's templates live in `backend/<id_>/emails.py` as `EMAILS`, found by that fixed name as `CSP` and `Settings` are (`harness/registry.py`, `tests/test_harness.py`); SPEC 4 and 7 and the module skills' layouts list it. `modules/_template` gets an empty `emails.py` with an example in its docstring rather than a live template.
- 2026-11-16 (the owner): SMTP is the first option, and Resend is used only where the host doesn't support SMTP, chosen at setup. `MAIL_ADAPTER` is gone: `SMTP_HOST` set means SMTP; `RESEND_API_KEY` without it means Resend; both set means SMTP, with a warning. An address or SMTP login with neither stops the start.
