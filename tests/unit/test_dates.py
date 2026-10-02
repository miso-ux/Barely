from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.dates import add_working_days, due_date_for, end_of_next_month

BA = ZoneInfo("Europe/Bratislava")


@pytest.mark.parametrize(
    ("issued", "expected"),
    [
        (date(2026, 10, 1), date(2026, 11, 30)),
        (date(2026, 10, 15), date(2026, 11, 30)),
        (date(2026, 10, 31), date(2026, 11, 30)),
        (date(2026, 12, 15), date(2027, 1, 31)),
        (date(2026, 11, 30), date(2026, 12, 31)),
        (date(2027, 1, 31), date(2027, 2, 28)),
        (date(2028, 1, 15), date(2028, 2, 29)),
    ],
)
def test_due_date_is_end_of_next_calendar_month(issued: date, expected: date) -> None:
    assert end_of_next_month(issued) == expected
    assert due_date_for(datetime.combine(issued, datetime.min.time(), tzinfo=BA)) == expected


def test_due_date_uses_local_calendar_not_utc() -> None:
    # 31 Oct 23:30 UTC is already 1 Nov 00:30 in Bratislava -> due end of December.
    late_evening_utc = datetime(2026, 10, 31, 23, 30, tzinfo=UTC)
    assert due_date_for(late_evening_utc) == date(2026, 12, 31)


def test_add_working_days_skips_weekends() -> None:
    friday = date(2026, 10, 2)
    assert add_working_days(friday, 1) == date(2026, 10, 5)  # Monday
    assert add_working_days(friday, 3) == date(2026, 10, 7)  # Wednesday
    assert add_working_days(friday, 0) == friday
