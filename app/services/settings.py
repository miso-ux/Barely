"""Business configuration stored in the `settings` table (FR-KO-01).

Values are JSON. Money is kept as a decimal string, never a float. `DEFAULTS` defines the
known keys, their default values and, implicitly, their types.
"""

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting, User
from app.services import audit
from app.services.errors import InvalidSettingValue, UnknownSetting

DEFAULTS: dict[str, Any] = {
    "max_items_per_order": 5,
    "penalty_amount": "10.00",
    "loan_limit": 10,
    "low_stock_threshold": 10,
    "due_reminder_days": 7,
    "block_debtors": True,
    "registration_enabled": False,
    "loan_price": "0.00",
    "forbidden_role_combinations": [
        ["warehouse", "invoicing"],
        ["supervisor", "warehouse"],
        ["supervisor", "invoicing"],
    ],
}

MONEY_KEYS = frozenset({"penalty_amount", "loan_price"})


def value_type(key: str) -> str:
    default = DEFAULTS[key]
    if key in MONEY_KEYS:
        return "money"
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, list):
        return "list"
    return "text"


def get(db: Session, key: str) -> Any:
    if key not in DEFAULTS:
        raise UnknownSetting(key=key)
    row = db.get(Setting, key)
    return row.value if row is not None else DEFAULTS[key]


def get_int(db: Session, key: str) -> int:
    return int(get(db, key))


def get_bool(db: Session, key: str) -> bool:
    return bool(get(db, key))


def get_decimal(db: Session, key: str) -> Decimal:
    return Decimal(str(get(db, key)))


def get_list(db: Session, key: str) -> list[Any]:
    return list(get(db, key))


def get_all(db: Session) -> list[Setting]:
    rows = {row.key: row for row in db.query(Setting).all()}
    return [rows.get(key) or Setting(key=key, value=DEFAULTS[key]) for key in DEFAULTS]


def parse(key: str, raw: str) -> Any:
    """Parse a form value according to the type of the default. Raises InvalidSettingValue."""
    kind = value_type(key)
    raw = raw.strip()
    try:
        if kind == "bool":
            if raw.lower() in {"true", "1", "on", "yes"}:
                return True
            if raw.lower() in {"false", "0", "off", "no"}:
                return False
            raise ValueError(raw)
        if kind == "int":
            value = int(raw)
            if value < 0:
                raise ValueError(raw)
            return value
        if kind == "money":
            value = Decimal(raw.replace(",", "."))
            if value < 0:
                raise ValueError(raw)
            return str(value.quantize(Decimal("0.01")))
        if kind == "list":
            value = json.loads(raw)
            if not isinstance(value, list):
                raise ValueError(raw)
            return value
        return raw
    except (ValueError, InvalidOperation, json.JSONDecodeError) as exc:
        raise InvalidSettingValue(key=key) from exc


def update(db: Session, *, actor: User, key: str, raw: str) -> Setting:
    if key not in DEFAULTS:
        raise UnknownSetting(key=key)
    new_value = parse(key, raw)
    row = db.get(Setting, key)
    old_value = row.value if row is not None else DEFAULTS[key]
    if row is None:
        row = Setting(key=key, value=new_value)
        db.add(row)
    else:
        row.value = new_value
    row.updated_by = actor.id
    audit.record(
        db,
        actor=actor,
        action="setting.changed",
        entity_type="setting",
        entity_id=key,
        before={"value": old_value},
        after={"value": new_value},
    )
    db.commit()
    return row


def ensure_defaults(db: Session) -> None:
    """Insert missing keys with default values. Existing values are never overwritten."""
    existing = {row.key for row in db.query(Setting).all()}
    for key, value in DEFAULTS.items():
        if key not in existing:
            db.add(Setting(key=key, value=value))
    db.commit()
