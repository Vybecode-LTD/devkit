"""Rate limits, per client address or per account (SPEC.md sections 6 and 14.6).

Lifted from VybeSite `core/ratelimit.py`, behind an interface a shared store
can back: counts live in `limits`' storage, memory:// for one process, and
redis://… once a site runs more than one (RATE_LIMIT_STORAGE). Moving
windows, so a burst at a window's edge isn't counted twice as small.

Rules are written `count/period`, the period a number and a unit: s, m, h or
d, such as "5/15m", "10/1m" or "3/1h".

**As a dependency**, on a route:

    @router.post("/sign-in", dependencies=[Depends(rate_limit("10/1m"))])
    @router.post("/ai/draft", dependencies=[Depends(rate_limit("20/1h", key="account"))])

Over the limit it answers 429 (`kernel.rate_limited`) with Retry-After.

**By hand**, for limits keyed on something in the body (an email typed) or
whose answer over the limit isn't a 429, through `request.app.state.limiter`:
`hit`, `used_up`, `wait_seconds`, `forget`.

**Who a request is** (`client_address`): the address in the header
CLIENT_IP_HEADER names, when it holds exactly one (Railway's edge writes
X-Real-IP itself), else the connection's. An IPv6 address counts as its
/64, since one subscriber usually holds a whole /64. `key="account"` uses the
signed-in user (`request.state.user_id`, set by auth) and falls back to the
address.
"""

from __future__ import annotations

import ipaddress
import math
import re
import time
from collections.abc import Awaitable, Callable
from typing import Literal, cast

from fastapi import Request
from limits import (
    RateLimitItem,
    RateLimitItemPerDay,
    RateLimitItemPerHour,
    RateLimitItemPerMinute,
    RateLimitItemPerSecond,
    storage,
)
from limits.aio.storage import Storage as AsyncStorage
from limits.aio.strategies import MovingWindowRateLimiter

from kernel.errors import Problem

_RULE = re.compile(r"^\s*(\d+)\s*/\s*(\d*)\s*([smhd])\s*$")
_UNITS: dict[str, type[RateLimitItem]] = {
    "s": RateLimitItemPerSecond,
    "m": RateLimitItemPerMinute,
    "h": RateLimitItemPerHour,
    "d": RateLimitItemPerDay,
}


def parse_rule(rule: str) -> RateLimitItem:
    """ "5/15m" as five per fifteen minutes. Raises ValueError otherwise."""
    match = _RULE.match(rule)
    if not match:
        raise ValueError(f"{rule!r} isn't a rate rule: count/period, such as 5/15m or 10/1h.")
    count, multiples, unit = int(match.group(1)), int(match.group(2) or 1), match.group(3)
    if count < 1 or multiples < 1:
        raise ValueError(f"{rule!r} must allow at least one request in at least one {unit}.")
    return _UNITS[unit](count, multiples)


def _async_uri(uri: str) -> str:
    return uri if uri.startswith("async+") else f"async+{uri}"


class RateLimiter:
    """Counts against named budgets: (scope, key) pairs under a rule."""

    def __init__(self, uri: str = "memory://", *, enabled: bool = True) -> None:
        self.enabled = enabled
        self._storage = cast(AsyncStorage, storage.storage_from_string(_async_uri(uri)))
        self._strategy = MovingWindowRateLimiter(self._storage)

    async def hit(self, rule: str, scope: str, key: str) -> bool:
        """Count one against `key` in `scope`. False when the budget was
        already spent (and nothing more is counted)."""
        if not self.enabled:
            return True
        return bool(await self._strategy.hit(parse_rule(rule), scope, key))

    async def used_up(self, rule: str, scope: str, key: str) -> bool:
        """Whether the budget is spent, counting nothing."""
        if not self.enabled:
            return False
        return not await self._strategy.test(parse_rule(rule), scope, key)

    async def wait_seconds(self, rule: str, scope: str, key: str) -> int:
        """Seconds until `key` may go again: 0 while under the limit."""
        if not await self.used_up(rule, scope, key):
            return 0
        stats = await self._strategy.get_window_stats(parse_rule(rule), scope, key)
        return max(1, math.ceil(stats.reset_time - time.time()))

    async def forget(self, rule: str, scope: str, key: str) -> None:
        """Start `key`'s count in `scope` again (a finished reset clears its
        sign-in failures, so the owner isn't refused for a stranger's guesses)."""
        if self.enabled:
            await self._strategy.clear(parse_rule(rule), scope, key)

    async def reset(self) -> None:
        """Forget every count (tests)."""
        await self._storage.reset()


def _header_address(
    request: Request, header: str
) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """The address in `header`, or None: missing, twice, or not one address
    isn't trusted (Railway's edge once passed a visitor's own beside its own)."""
    if not header.strip():
        return None
    values = request.headers.getlist(header.strip())
    if len(values) != 1:
        return None
    try:
        return ipaddress.ip_address(values[0].strip())
    except ValueError:
        return None


def client_address(request: Request) -> str:
    """Who a request comes from, for limits per client: an IPv4 address or an
    IPv6 /64."""
    header = getattr(request.app.state, "client_ip_header", "")
    address = _header_address(request, header)
    if address is None:
        host = request.client.host if request.client else ""
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return host or "unknown"
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def account_or_address(request: Request) -> str:
    """The signed-in account, else the address."""
    user_id = getattr(request.state, "user_id", None)
    return f"account:{user_id}" if user_id else client_address(request)


KeyFunc = Callable[[Request], str]


def rate_limit(
    rule: str,
    *,
    key: Literal["ip", "account"] | KeyFunc = "ip",
    scope: str | None = None,
) -> Callable[[Request], Awaitable[None]]:
    """A dependency that answers 429 once `key` has spent `rule` in `scope`.
    Routes sharing a scope share one budget; without one each route has its
    own (its method and path)."""
    parse_rule(rule)  # a bad rule fails at import, not at the first request
    key_func: KeyFunc = (
        client_address if key == "ip" else account_or_address if key == "account" else key
    )

    async def limited(request: Request) -> None:
        limiter: RateLimiter = request.app.state.limiter
        route = request.scope.get("route")
        name = scope or f"{request.method} {getattr(route, 'path', request.url.path)}"
        who = key_func(request)
        if not await limiter.hit(rule, name, who):
            wait = await limiter.wait_seconds(rule, name, who)
            raise Problem(
                "kernel.rate_limited",
                429,
                "Too many requests. Wait a moment, then try again.",
                headers={"Retry-After": str(wait)},
                extra={"retry_after": wait},
            )

    return limited
