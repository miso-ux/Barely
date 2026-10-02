"""Debtor rules (BR-15). Penalties and overdue handling arrive in phase 4; until then no one is a
debtor. Orders already call this hook so the block works the moment phase 4 lands."""

from sqlalchemy.orm import Session

from app.models import User


def is_debtor(db: Session, user: User) -> bool:
    return False
