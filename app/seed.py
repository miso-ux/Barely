"""Idempotent demo seed. Runs on every container start; must be safe to repeat.

Syncs the permission catalogue and role bundles, inserts missing settings, and creates demo
accounts that do not exist yet. Existing accounts (and their changed passwords) are left alone.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.permissions import PERMISSIONS, ROLE_PERMISSIONS, ROLES
from app.db import SessionLocal
from app.models import (
    Barrel,
    BarrelStatus,
    CustomerType,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import audit, barrel_state
from app.services import barrels as barrels_service
from app.services import settings as settings_service
from app.services.barrel_state import Reason

# Demo only. Documented in README; never use real passwords here.
DEMO_PASSWORD = "Demo1234!"

# (username, display name, role code, must change password at first login)
DEMO_USERS: list[tuple[str, str, str, bool]] = [
    ("admin", "Správca systému", "super_admin", True),
    ("warehouse", "Skladník Demo", "warehouse", False),
    ("invoicing", "Fakturant Demo", "invoicing", False),
    ("supervisor", "Supervízor Demo", "supervisor", False),
    ("user", "Používateľ Demo", "user", False),
    ("jana.novakova", "Jana Nováková", "user", False),
    ("peter.horvath", "Peter Horváth", "user", False),
]


def sync_permissions(db: Session) -> dict[str, Permission]:
    existing = {p.code: p for p in db.scalars(select(Permission))}
    for code, description in PERMISSIONS.items():
        if code in existing:
            existing[code].description = description
        else:
            perm = Permission(code=code, description=description)
            db.add(perm)
            existing[code] = perm
    db.flush()
    return existing


def sync_roles(db: Session) -> dict[str, Role]:
    existing = {r.code: r for r in db.scalars(select(Role))}
    for code, name_key in ROLES.items():
        if code in existing:
            existing[code].name_key = name_key
        else:
            role = Role(code=code, name_key=name_key)
            db.add(role)
            existing[code] = role
    db.flush()
    return existing


def sync_role_permissions(
    db: Session, roles: dict[str, Role], permissions: dict[str, Permission]
) -> None:
    desired = {
        (roles[role_code].id, permissions[perm_code].id)
        for role_code, perm_codes in ROLE_PERMISSIONS.items()
        for perm_code in perm_codes
    }
    current = {(rp.role_id, rp.permission_id) for rp in db.scalars(select(RolePermission))}
    for role_id, permission_id in current - desired:
        db.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
    for role_id, permission_id in desired - current:
        db.add(RolePermission(role_id=role_id, permission_id=permission_id))
    db.flush()


def seed_demo_users(db: Session, roles: dict[str, Role]) -> int:
    existing = set(db.scalars(select(User.username)))
    password_hash = hash_password(DEMO_PASSWORD)  # hash once, Argon2 is deliberately slow
    created = 0
    for username, display_name, role_code, must_change in DEMO_USERS:
        if username in existing:
            continue
        user = User(
            username=username,
            display_name=display_name,
            password_hash=password_hash,
            customer_type=CustomerType.INTERNAL,
            is_active=True,
            must_change_password=must_change,
        )
        user.user_roles = [UserRole(role=roles[role_code])]
        db.add(user)
        db.flush()
        audit.record(
            db,
            actor=None,
            action="user.created",
            entity_type="user",
            entity_id=user.id,
            after={"username": username, "roles": [role_code], "source": "seed"},
        )
        created += 1
    return created


DEMO_BARREL_COUNT = 30


def seed_demo_barrels(db: Session) -> int:
    """Demo stock, created only when the registry is empty.

    Loan counts are spread so the automatic barrel selection (phase 3) is visible, and a few
    barrels sit in the other statuses so every state shows up on the dashboard.
    """
    if db.scalar(select(func.count()).select_from(Barrel)):
        return 0
    barrels = barrels_service.create_barrels(db, actor=None, count=DEMO_BARREL_COUNT)
    for index, barrel in enumerate(barrels):
        barrel.loan_count = (index * 7) % 10  # 0..9 in a scrambled order
    S = BarrelStatus
    barrel_state.transition(
        db,
        barrels[-4],
        S.DAMAGED,
        actor=None,
        reason=Reason.DAMAGED,
        note="Prasknuté hrdlo pri kontrole na sklade",
    )
    barrel_state.transition(
        db, barrels[-3], S.LOST, actor=None, reason=Reason.LOST, note="Nenájdený pri inventúre"
    )
    barrels[-2].loan_count = 10
    barrel_state.transition(db, barrels[-2], S.ON_LOAN, actor=None, reason=Reason.ISSUED)
    barrel_state.transition(db, barrels[-2], S.RETIRED, actor=None, reason=Reason.RETIRED)
    barrel_state.transition(
        db,
        barrels[-1],
        S.WRITTEN_OFF,
        actor=None,
        reason=Reason.WRITTEN_OFF,
        note="Poškodený pri preprave",
    )
    db.commit()
    return len(barrels)


def run(quiet: bool = False) -> None:
    with SessionLocal() as db:
        permissions = sync_permissions(db)
        roles = sync_roles(db)
        sync_role_permissions(db, roles, permissions)
        db.commit()
        settings_service.ensure_defaults(db)
        created = seed_demo_users(db, roles)
        db.commit()
        barrels_created = seed_demo_barrels(db)
    if not quiet:
        print(
            f"seed: roles and permissions synced, {created} demo user(s) created, "
            f"{barrels_created} demo barrel(s) created"
        )


if __name__ == "__main__":
    run()
