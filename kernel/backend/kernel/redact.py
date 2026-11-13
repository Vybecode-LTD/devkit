"""Takes what's private out of text before it reaches a log or the error tracker.

Lifted from VybeSite `core/error_tracking.py` (`clean_text`), without its
campaign-tracking patterns. It is a backstop, not a licence: the kernel never
logs a password, code, token or secret on purpose, and this catches the
shapes that slip through anyway. Removed from any string:

- the values a database error carries (SQLAlchemy's `[parameters: …]`,
  Postgres's `Key (…)=(…)` and `Failing row contains (…)`) and Pydantic's
  `input_value=…`;
- credentials in a URL (`postgres://user:pass@host`), and the value after
  `password=`, `secret=`, `token=` or `code=`;
- email addresses, the query of a URL or path, IP addresses other than the
  loopback and unspecified ones (a server's own bind address), and the hash
  prefix of a Pwned Passwords lookup (`/range/ABCDE`);
- JSON Web Tokens, Stripe-style keys (`sk_live_…`, `whsec_…`), and any run
  of 32 token-like characters that isn't a UUID or a snake_case name.

It misses what has no shape, such as a six-digit code alone. A string past
MAX_TEXT keeps its first 2,048 characters and its end, cut at whitespace,
since a traceback's last line is the one that names the error. Every pattern
runs in linear time: this runs on the event loop.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

REDACTED = "[redacted]"
ADDRESS = "[address]"
MAX_TEXT = 8192
_HEAD = 2048
_MARK_ROOM = 40  # "\n…[n characters cut]…\n", so the whole stays within MAX_TEXT

_DETAIL_END = r"(?:(?=\nHINT:  |\n\[SQL: |\n\(Background on this error at: )|\Z)"
_SQL_PARAMETERS = re.compile(r"\[parameters: (?s:.*?)(?:(?=\n\(Background on this error at: )|\Z)")
_KEY_VALUE = re.compile(r"(Key \((?:[^()\n]|\([^()\n]*\))*+\)=\()((?s:.*?))" + _DETAIL_END)
_FAILING_ROW = re.compile(r"Failing row contains \(((?s:.*?))" + _DETAIL_END)
_KEY_TAIL = re.compile(
    r'\) (?:already exists|is (?:not present in|still referenced from) table "[^"\n]*")\.?'
)
# Possessive and bounded: a run like "a.a.a." is scanned once, not once per start.
_URL_CREDENTIALS = re.compile(r"(?<![A-Za-z0-9+.\-])([A-Za-z][A-Za-z0-9+.\-]{0,31}+://)[^\s/@]++@")
_EMAIL = re.compile(r"(?<![\w.%+'\-])[\w.%+'\-]+(?:@|%40)[\w\-]+(?:\.[\w\-]+)*\.[^\W\d_]{2,}")
_QUERY = re.compile(r"(?<![^\s\"'(<\[=,:])((?:https?://|/)[^\s?#\"']*+)\?[^\s#\"']*")
_NAMED_SECRET = re.compile(r"(?i)\b(password|passwd|secret|token|code)=[^\s&,;\"'\]]++")
_INPUT_VALUE = re.compile(r"""\binput_value=(?:'(?:[^'\\]|\\.)*+'|"(?:[^"\\]|\\.)*+"|[^\s,\]]++)""")
_BREACH_RANGE = re.compile(r"/range/[0-9A-Fa-f]{5}\b")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]{4,}+\.[A-Za-z0-9_\-]{4,}+\.[A-Za-z0-9_\-]*+")
_KEYED = re.compile(r"\b(?:(?:sk|rk)_(?:live|test)|whsec)_[A-Za-z0-9]++")
_IP_CANDIDATE = re.compile(r"(?<![\w:.])[0-9A-Fa-f:.]{7,}(?:/\d{1,3})?(?![\w:.])")
_TOKENISH = re.compile(r"[A-Za-z0-9_\-]{32,}")
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_SNAKE = re.compile(r"[a-z_]+")


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def _is_own(text: str) -> bool:
    """The loopback or unspecified address: a server's own, never a visitor's."""
    address = ipaddress.ip_address(text)
    return address.is_loopback or address.is_unspecified


def _ip(match: re.Match[str]) -> str:
    """An IP address (with a port or a prefix length), or the text as it was:
    a time like 12:30:45 is no address. A full stop after it ends a sentence."""
    text = match.group(0)
    stop = len(text) - len(text.rstrip("."))
    text = text[: len(text) - stop]
    bare = text.split("/", 1)[0]
    if _is_ip(bare):
        return text + "." * stop if _is_own(bare) else REDACTED + "." * stop
    host, _, port = bare.rpartition(":")
    if port.isdigit() and "." in host and _is_ip(host):
        return text + "." * stop if _is_own(host) else REDACTED + "." * stop
    return text + "." * stop


def _key_value(match: re.Match[str]) -> str:
    values = match.group(2)
    cut = values.rfind(") ")
    tail = values[cut:] if cut >= 0 and _KEY_TAIL.fullmatch(values[cut:]) else ")"
    return f"{match.group(1)}{REDACTED}{tail}"


def _failing_row(match: re.Match[str]) -> str:
    return f"Failing row contains ({REDACTED})" + ("." if match.group(1).endswith(").") else "")


def _token_or_name(match: re.Match[str]) -> str:
    text = match.group(0)
    return text if _UUID.fullmatch(text) or _SNAKE.fullmatch(text) else REDACTED


def _cut(text: str) -> str:
    """The head and the end of a long string, cut at a line break where one
    is near (else a space), so no word, address or token is left in half."""
    if len(text) <= MAX_TEXT:
        return text
    head_end = _HEAD
    for mark in ("\n", " "):
        found = text.rfind(mark, 0, _HEAD)
        if found > _HEAD // 2:
            head_end = found
            break
    tail_from = len(text) - (MAX_TEXT - head_end - _MARK_ROOM)
    for mark in ("\n", " "):
        found = text.find(mark, tail_from, tail_from + _HEAD)
        if found >= 0:
            tail_from = found + 1
            break
    cut = tail_from - head_end
    return f"{text[:head_end]}\n…[{cut} characters cut]…\n{text[tail_from:]}"


def clean_text(text: str) -> str:
    """A string with nothing private left in it (this module's list)."""
    text = _cut(text)
    text = _SQL_PARAMETERS.sub("[parameters: hidden]", text)
    text = _KEY_VALUE.sub(_key_value, text)
    text = _FAILING_ROW.sub(_failing_row, text)
    text = _INPUT_VALUE.sub(f"input_value={REDACTED}", text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{REDACTED}@", text)
    text = _EMAIL.sub(ADDRESS, text)
    text = _QUERY.sub(lambda m: f"{m.group(1)}?{REDACTED}", text)
    text = _NAMED_SECRET.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    text = _BREACH_RANGE.sub(f"/range/{REDACTED}", text)
    text = _JWT.sub(REDACTED, text)
    text = _KEYED.sub(REDACTED, text)
    text = _IP_CANDIDATE.sub(_ip, text)
    return _TOKENISH.sub(_token_or_name, text)


def clean(value: Any) -> Any:
    """`clean_text` on every string in a value, keys of a dict included."""
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict):
        return {
            clean_text(key) if isinstance(key, str) else key: clean(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [clean(item) for item in value]
    return value
