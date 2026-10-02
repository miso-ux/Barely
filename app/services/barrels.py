"""Barrel registry: adding barrels, manual status changes, stock overview (FR-BA, FR-SK)."""

import re
from typing import Final

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Barrel, BarrelStatus, User
from app.services import barrel_state
from app.services import settings as settings_service
from app.services.barrel_state import Reason
from app.services.errors import (
    BarrelCodeTaken,
    InvalidBarrelCode,
    InvalidBarrelTransition,
    InvalidCount,
    ReasonRequired,
)

MAX_BULK_CREATE: Final = 500
CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,49}$")

# Manual changes a warehouse worker may make, and the history reason recorded for each.
MANUAL_CHANGES: Final[dict[BarrelStatus, str]] = {
    BarrelStatus.DAMAGED: Reason.DAMAGED,
    BarrelStatus.LOST: Reason.LOST,
    BarrelStatus.WRITTEN_OFF: Reason.WRITTEN_OFF,
    BarrelStatus.IN_STOCK: Reason.FOUND,  # only from `lost`
}
# How many loans below the limit a barrel counts as "approaching the limit" (FR-BA-11).
NEAR_LIMIT_MARGIN: Final = 2


def next_code(db: Session) -> str:
    number = db.execute(text("SELECT nextval('barrel_code_seq')")).scalar_one()
    return f"B-{number:04d}"


def get_by_code(db: Session, code: str) -> Barrel | None:
    return db.scalar(select(Barrel).where(Barrel.code == code))


def create_barrels(
    db: Session, *, actor: User | None, count: int = 1, code: str | None = None
) -> list[Barrel]:
    """Add barrels. Codes are generated unless a single barrel with a custom code is added."""
    if count < 1 or count > MAX_BULK_CREATE:
        raise InvalidCount(max=MAX_BULK_CREATE)
    code = (code or "").strip()
    if code:
        if count != 1:
            raise InvalidCount(max=1)
        if not CODE_RE.match(code):
            raise InvalidBarrelCode()
        if get_by_code(db, code) is not None:
            raise BarrelCodeTaken(code=code)

    barrels: list[Barrel] = []
    for _ in range(count):
        barrel = Barrel(code=code or next_code(db), status=BarrelStatus.IN_STOCK, loan_count=0)
        db.add(barrel)
        db.flush()
        barrel_state.record_creation(db, barrel, actor=actor)
        barrels.append(barrel)
    db.commit()
    return barrels


def change_status_manually(
    db: Session, *, actor: User, barrel: Barrel, to_status: BarrelStatus, note: str
) -> Barrel:
    """Warehouse action: damaged / lost / written off with a mandatory reason, or found."""
    if to_status not in MANUAL_CHANGES:
        raise InvalidBarrelTransition(from_status=barrel.status.value, to_status=to_status.value)
    if to_status is BarrelStatus.IN_STOCK and barrel.status is not BarrelStatus.LOST:
        # Returning to stock by hand is only for found barrels; loans return via phase 4.
        raise InvalidBarrelTransition(from_status=barrel.status.value, to_status=to_status.value)
    if to_status is not BarrelStatus.IN_STOCK and not note.strip():
        raise ReasonRequired()
    barrel_state.transition(
        db, barrel, to_status, actor=actor, reason=MANUAL_CHANGES[to_status], note=note
    )
    db.commit()
    return barrel


def manual_targets(barrel: Barrel) -> list[BarrelStatus]:
    """Which manual changes the UI should offer for this barrel."""
    return [
        status
        for status in MANUAL_CHANGES
        if barrel_state.can_transition(barrel.status, status)
        and (status is not BarrelStatus.IN_STOCK or barrel.status is BarrelStatus.LOST)
    ]


def list_barrels(db: Session, *, status: BarrelStatus | None = None) -> list[Barrel]:
    stmt = select(Barrel).order_by(Barrel.code)
    if status is not None:
        stmt = stmt.where(Barrel.status == status)
    return list(db.scalars(stmt))


def status_counts(db: Session) -> dict[BarrelStatus, int]:
    rows = db.execute(select(Barrel.status, func.count()).group_by(Barrel.status)).all()
    counts = dict.fromkeys(BarrelStatus, 0)
    for status, count in rows:
        counts[status] = count
    return counts


def reserved_count(db: Session) -> int:
    """Pieces reserved by pending orders. Orders arrive in phase 3; nothing is reserved yet."""
    return 0


def free_count(db: Session) -> int:
    """FR-SK-02: barrels in stock minus pieces in active reservations."""
    in_stock = db.scalar(
        select(func.count()).select_from(Barrel).where(Barrel.status == BarrelStatus.IN_STOCK)
    )
    return max(int(in_stock or 0) - reserved_count(db), 0)


def near_limit(db: Session) -> list[Barrel]:
    """Barrels still in circulation whose loan count is close to the configured limit."""
    limit = settings_service.get_int(db, "loan_limit")
    threshold = max(limit - NEAR_LIMIT_MARGIN, 0)
    stmt = (
        select(Barrel)
        .where(
            Barrel.status.in_([BarrelStatus.IN_STOCK, BarrelStatus.ON_LOAN]),
            Barrel.loan_count >= threshold,
        )
        .order_by(Barrel.loan_count.desc(), Barrel.added_at)
    )
    return list(db.scalars(stmt))
