"""Daily maintenance job (NFR-06). Phase 3: expire stale reservations (Q-03).

Phase 4 adds overdue penalties, due-date reminders and debtor marking, plus the in-process
scheduler. Until then run it by hand: `python -m app.jobs.daily`.
"""

from app.db import SessionLocal
from app.services import orders


def run(quiet: bool = False) -> dict[str, int]:
    with SessionLocal() as db:
        expired = orders.expire_reservations(db)
    summary = {"expired_reservations": len(expired)}
    if not quiet:
        print(f"daily: {summary}")
    return summary


if __name__ == "__main__":
    run()
