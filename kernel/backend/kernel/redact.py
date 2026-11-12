"""Takes what's private out of text before it reaches a log or the error tracker.

Lifted from VybeSite `core/error_tracking.py` (`clean_text`), without its
campaign-tracking patterns. Removed from any string:

- the values a database error carries (SQLAlchemy's `[parameters: …]`,
  Postgres's `Key (…)=(…)` and `Failing row contains (…)`);
- credentials in a URL (`postgres://user:pass@host`);
- email addresses, the query of a URL or path, IP addresses;
- any run of 32 token-like characters that isn't a UUID or a snake_case name.

Strings are cut at MAX_TEXT first, and every pattern runs in linear time:
this runs on the event loop.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

REDACTED = "[redacted]"
ADDRESS = "[address]"
MAX_TEXT = 8192

_DETAIL_END = r"(?:(?=\nHINT:  |\n\[SQL: |\n\(Background on this error at: )|\Z)"
_SQL_PARAMETERS = re.compile(r"\[parameters: (?s:.*?)(?:(?=\n\(Background on this error at: )|\Z)")
_KEY_VALUE = re.compile(r"(Key \((?:[^()\n]|\([^()\n]*\))*+\)=\()((?s:.*?))" + _DETAIL_END)
_FAILING_ROW = re.compile(r"Failing row contains \(((?s:.*?))" + _DETAIL_END)
_KEY_TAIL = re.compile(
    r'\) (?:already exists|is (?:not present in|still referenced from) table "[^"\n]*")\.?'
)
_URL_CREDENTIALS = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.\-]*://)[^\s/@]+@")
_EMAIL = re.compile(r"(?<![\w.%+'\-])[\w.%+'\-]+(?:@|%40)[\w\-]+(?:\.[\w\-]+)*\.[^\W\d_]{2,}")
_QUERY = re.compile(r"(?<![^\s\"'(<\[=,])((?:https?://|/)[^\s?#\"']*+)\?[^\s#\"']*")
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


def _ip(match: re.Match[str]) -> str:
    """An IP address (with a port or a prefix length), or the text as it was:
    a time like 12:30:45 is no address."""
    text = match.group(0)
    bare = text.split("/", 1)[0]
    if _is_ip(bare):
        return REDACTED
    host, _, port = bare.rpartition(":")
    if port.isdigit() and "." in host and _is_ip(host):
        return REDACTED
    return text


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


def clean_text(text: str) -> str:
    """A string with nothing private left in it (this module's list)."""
    text = text[:MAX_TEXT]
    text = _SQL_PARAMETERS.sub("[parameters: hidden]", text)
    text = _KEY_VALUE.sub(_key_value, text)
    text = _FAILING_ROW.sub(_failing_row, text)
    text = _URL_CREDENTIALS.sub(lambda m: f"{m.group(1)}{REDACTED}@", text)
    text = _EMAIL.sub(ADDRESS, text)
    text = _QUERY.sub(lambda m: f"{m.group(1)}?{REDACTED}", text)
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
