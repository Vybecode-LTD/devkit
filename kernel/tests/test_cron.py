"""kernel.cron: five-field cron lines, UTC, for the jobs' scheduler (contract
k3-jobs, decision 0035). No database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kernel import cron


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    ("line", "yes", "no"),
    [
        ("* * * * *", "2026-11-16T10:07", None),
        ("*/5 * * * *", "2026-11-16T10:05", "2026-11-16T10:07"),
        ("7 * * * *", "2026-11-16T03:07", "2026-11-16T03:08"),
        ("0 3 * * *", "2026-11-16T03:00", "2026-11-16T04:00"),
        ("0-10/5 * * * *", "2026-11-16T03:10", "2026-11-16T03:15"),
        ("1,2,30 * * * *", "2026-11-16T03:30", "2026-11-16T03:31"),
        ("0 9-17 * * *", "2026-11-16T17:00", "2026-11-16T18:00"),
        ("0 0 1 * *", "2026-12-01T00:00", "2026-12-02T00:00"),
        ("0 0 * 2 *", "2027-02-11T00:00", "2027-03-11T00:00"),
        # 2026-11-16 is a Monday; Sunday is 0 and 7.
        ("0 0 * * 1", "2026-11-16T00:00", "2026-11-17T00:00"),
        ("0 0 * * 0", "2026-11-15T00:00", "2026-11-16T00:00"),
        ("0 0 * * 7", "2026-11-15T00:00", "2026-11-16T00:00"),
        ("0 0 * * 1-5", "2026-11-20T00:00", "2026-11-21T00:00"),
        # Both day fields restricted: either matches, as cron does.
        ("0 0 13 * 5", "2026-11-13T00:00", "2026-11-12T00:00"),
        ("0 0 13 * 5", "2026-11-20T00:00", None),
        # One day field starting with *: only the other one counts.
        # 2026-11-23 is a Monday on an odd day; 2026-11-16 a Monday on an even one.
        ("0 0 */2 * 1", "2026-11-23T00:00", "2026-11-16T00:00"),
    ],
)
def test_a_line_matches_its_minutes(line: str, yes: str, no: str | None) -> None:
    parsed = cron.parse(line)
    assert parsed.matches(at(yes))
    if no is not None:
        assert not parsed.matches(at(no))


def test_seconds_never_matter() -> None:
    assert cron.parse("5 * * * *").matches(at("2026-11-16T10:05:59"))


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ("", "five fields"),
        ("* * * *", "five fields"),
        ("* * * * * *", "five fields"),
        ("60 * * * *", "minute"),
        ("* 24 * * *", "hour"),
        ("* * 0 * *", "day of the month"),
        ("* * 32 * *", "day of the month"),
        ("* * * 13 *", "month"),
        ("* * * * 8", "day of the week"),
        ("*/0 * * * *", "minute"),
        ("5-1 * * * *", "minute"),
        ("* * * jan *", "month"),
        ("* * * * mon", "day of the week"),
        ("* * L * *", "day of the month"),
        ("* * 1W * *", "day of the month"),
        ("* * * * 1#2", "day of the week"),
        ("* * ? * *", "day of the month"),
        ("1,,2 * * * *", "minute"),
        ("-1 * * * *", "minute"),
        ("+1 * * * *", "minute"),
        (chr(0x0661) + " * * * *", "minute"),  # an Arabic-Indic 1, which int() would take
    ],
)
def test_a_bad_line_is_refused_by_field(line: str, field: str) -> None:
    with pytest.raises(ValueError, match=field):
        cron.parse(line)


def test_the_refusal_names_the_line() -> None:
    with pytest.raises(ValueError, match=r"'61 \* \* \* \*'"):
        cron.parse("61 * * * *")


def test_extra_spaces_between_fields_are_fine() -> None:
    assert cron.parse("  */5   *  * * *  ").matches(at("2026-11-16T10:05"))


def test_the_latest_slot_is_the_newest_match_after_the_last_one() -> None:
    line = cron.parse("*/5 * * * *")
    assert line.latest(at("2026-11-16T10:07:30"), after=at("2026-11-16T09:00")) == at(
        "2026-11-16T10:05"
    )


def test_the_latest_slot_can_be_now() -> None:
    line = cron.parse("*/5 * * * *")
    assert line.latest(at("2026-11-16T10:05:00"), after=at("2026-11-16T10:00")) == at(
        "2026-11-16T10:05"
    )


def test_a_slot_at_or_before_the_last_one_isnt_new() -> None:
    line = cron.parse("*/5 * * * *")
    assert line.latest(at("2026-11-16T10:07"), after=at("2026-11-16T10:05")) is None


@pytest.mark.parametrize(
    ("line", "now", "expected"),
    [
        ("0 0 1 * *", "2026-12-03T08:00", "2026-12-01T00:00"),
        ("0 0 1 1 *", "2027-01-02T00:00", "2027-01-01T00:00"),
        ("59 23 31 12 *", "2027-01-01T00:30", "2026-12-31T23:59"),
        ("0 0 29 2 *", "2028-03-01T00:00", "2028-02-29T00:00"),
        ("30 2 * * 0", "2026-11-18T12:00", "2026-11-15T02:30"),
    ],
)
def test_the_latest_slot_across_day_month_and_year_ends(line: str, now: str, expected: str) -> None:
    parsed = cron.parse(line)
    found = parsed.latest(at(now), after=at(now) - timedelta(days=7))
    assert found == at(expected)


def test_no_slot_within_the_window_is_none() -> None:
    # 29 February next falls in 2028: nothing in the week before 2027-03-01.
    parsed = cron.parse("0 0 29 2 *")
    now = at("2027-03-01T00:00")
    assert parsed.latest(now, after=now - timedelta(days=7)) is None


def test_the_latest_slot_wants_an_aware_time() -> None:
    with pytest.raises(ValueError, match="UTC"):
        cron.parse("* * * * *").latest(datetime(2026, 11, 16, 10, 0), after=at("2026-11-16T09:00"))


def test_a_time_in_another_zone_is_read_as_utc() -> None:
    from datetime import timezone

    eastern = timezone(timedelta(hours=-5))
    local = datetime(2026, 11, 16, 5, 0, tzinfo=eastern)  # 10:00 UTC
    assert cron.parse("0 10 * * *").matches(local)
