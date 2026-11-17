"""Five-field cron lines, in UTC, for the jobs' scheduler (contract k3-jobs,
decision 0035). No dependency.

    minute (0-59)  hour (0-23)  day of the month (1-31)  month (1-12)  day of the week (0-7)

Each field is `*`, a number, a range `a-b`, either one with a step (`*/5`,
`0-30/10`), or a comma-separated list of those. Sunday is 0 and 7. Names
(`jan`, `mon`), seconds and the extensions `L`, `W`, `#` and `?` are refused:
a line that means something else in another cron is worse than one refused.

When both day fields are restricted, a day matching either one matches, as
cron does; when one of them starts with `*`, only the other counts (so
`0 0 */2 * 1` is Mondays that fall on an odd day of the month).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

#: (name, lowest, highest) for each field, in order.
_FIELDS = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day of the month", 1, 31),
    ("month", 1, 12),
    ("day of the week", 0, 7),
)
_DIGITS = frozenset("0123456789")


def _number(text: str, field: str, line: str) -> int:
    # ASCII digits only: int() also takes other scripts' digits and signs.
    if not text or not set(text) <= _DIGITS or len(text) > 2:
        raise ValueError(f"The cron line {line!r} has a bad {field}: {text!r} isn't a number.")
    return int(text)


def _field(text: str, field: str, lowest: int, highest: int, line: str) -> frozenset[int]:
    values: set[int] = set()
    for part in text.split(","):
        span, slash, step_text = part.partition("/")
        step = _number(step_text, field, line) if slash else 1
        if step < 1:
            raise ValueError(f"The cron line {line!r} has a bad {field}: a step of 0.")
        if span == "*":
            start, end = lowest, highest
        elif "-" in span:
            first, _, last = span.partition("-")
            start, end = _number(first, field, line), _number(last, field, line)
        else:
            start = _number(span, field, line)
            end = highest if slash else start
        if not lowest <= start <= end <= highest:
            raise ValueError(
                f"The cron line {line!r} has a bad {field}: {part!r} isn't within {lowest} to {highest}."
            )
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class Cron:
    line: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]  # 0 is Sunday; a 7 is read as 0
    days_unrestricted: bool
    weekdays_unrestricted: bool

    def _day(self, at: datetime) -> bool:
        if at.month not in self.months:
            return False
        day, weekday = at.day in self.days, at.isoweekday() % 7 in self.weekdays
        if self.days_unrestricted or self.weekdays_unrestricted:
            return day and weekday
        return day or weekday

    def matches(self, at: datetime) -> bool:
        """Whether `at`'s minute is one of the line's, in UTC."""
        at = _utc(at)
        return at.minute in self.minutes and at.hour in self.hours and self._day(at)

    def latest(self, at: datetime, *, after: datetime) -> datetime | None:
        """The newest minute in (`after`, `at`] that matches, or None. Walks
        back an hour at a time, so a week's window costs a few hundred steps."""
        at, after = _utc(at), _utc(after)
        minute = at.replace(second=0, microsecond=0)
        hour = minute.replace(minute=0)
        while hour + timedelta(minutes=59) > after:
            if hour.hour in self.hours and self._day(hour):
                for value in sorted(self.minutes, reverse=True):
                    candidate = hour.replace(minute=value)
                    if after < candidate <= minute:
                        return candidate
            hour -= timedelta(hours=1)
        return None


def _utc(at: datetime) -> datetime:
    if at.tzinfo is None:
        raise ValueError("A cron time must say its zone: give a UTC datetime.")
    return at.astimezone(UTC)


def parse(line: str) -> Cron:
    """The line as a `Cron`; ValueError naming the line and the field."""
    parts = line.split()
    if len(parts) != len(_FIELDS):
        raise ValueError(
            f"The cron line {line!r} must have five fields: minute hour day month weekday."
        )
    parsed = [
        _field(text, field, lowest, highest, line)
        for text, (field, lowest, highest) in zip(parts, _FIELDS, strict=True)
    ]
    weekdays = frozenset(0 if value == 7 else value for value in parsed[4])
    return Cron(
        line=" ".join(parts),
        minutes=parsed[0],
        hours=parsed[1],
        days=parsed[2],
        months=parsed[3],
        weekdays=weekdays,
        days_unrestricted=parts[2].startswith("*"),
        weekdays_unrestricted=parts[4].startswith("*"),
    )
