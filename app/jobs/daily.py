"""Daily maintenance job (NFR-06, FR-VR-04, FR-VR-09, Q-03).

Runs once a day from the in-process scheduler (see app.main) and can be triggered by hand:
`python -m app.jobs.daily` or the button on the warehouse dashboard. Every step is idempotent,
so running it twice on the same day changes nothing the second time.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services import loans, orders


def run_with_session(db: Session, *, today: date | None = None) -> dict[str, int]:
    expired = orders.expire_reservations(db, today=today)
    overdue = loans.mark_overdue(db, today=today)
    reminded = loans.send_due_reminders(db, today=today)
    return {
        "expired_reservations": len(expired),
        "overdue_loans": len(overdue),
        "reminders_sent": len(reminded),
    }


def run(quiet: bool = False) -> dict[str, int]:
    with SessionLocal() as db:
        summary = run_with_session(db)
    if not quiet:
        print(f"daily: {summary}")
    return summary


if __name__ == "__main__":
    run()
