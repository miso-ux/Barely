"""Calendar rules. Timestamps are UTC; business dates are in the configured local zone (NFR-05)."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings


def _zone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now_utc() -> datetime:
    return datetime.now(UTC)


def local_date(moment: datetime) -> date:
    return moment.astimezone(_zone()).date()


def today_local() -> date:
    return local_date(now_utc())


def end_of_next_month(day: date) -> date:
    """BR-02: the last day of the month after `day`'s month."""
    year, month = day.year, day.month + 2
    while month > 12:
        month -= 12
        year += 1
    return date(year, month, 1) - timedelta(days=1)


def due_date_for(issued_at: datetime) -> date:
    return end_of_next_month(local_date(issued_at))


def add_working_days(day: date, count: int) -> date:
    """Monday to Friday only; public holidays are not considered."""
    result = day
    remaining = count
    while remaining > 0:
        result += timedelta(days=1)
        if result.weekday() < 5:
            remaining -= 1
    return result


def format_date(day: date | None) -> str:
    return day.strftime("%d.%m.%Y") if day else ""
