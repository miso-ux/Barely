"""User accounts, roles and passwords (FR-US-01 to FR-US-13).

Role assignments are configuration, not domain records, so re-assigning roles replaces the
`user_roles` rows. Every change is captured with before/after values in the audit log.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import (
    generate_temporary_password,
    hash_password,
    validate_password,
    verify_password,
)
from app.models import CustomerType, Role, User, UserRole
from app.services import audit
from app.services import settings as settings_service
from app.services.errors import (
    ForbiddenRoleCombination,
    InvalidCredentials,
    InvalidUsername,
    NoRoleSelected,
    RegistrationDisabled,
    SelfDeactivation,
    SelfRoleChange,
    UnknownRole,
    UsernameTaken,
    WrongCurrentPassword,
)

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")


def normalize_username(username: str) -> str:
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise InvalidUsername()
    return username


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username.strip().lower()))


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.id)))


def authenticate(db: Session, username: str, password: str) -> User:
    user = get_by_username(db, username)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        audit.record(
            db,
            actor=None,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else None,
            after={"username": username.strip().lower()},
        )
        db.commit()
        raise InvalidCredentials()
    audit.record(db, actor=user, action="auth.login", entity_type="user", entity_id=user.id)
    db.commit()
    return user


def _check_role_combination(db: Session, codes: set[str]) -> None:
    for combo in settings_service.get_list(db, "forbidden_role_combinations"):
        if set(combo) <= codes:
            raise ForbiddenRoleCombination(roles=", ".join(combo))


def _resolve_roles(db: Session, role_codes: list[str]) -> list[Role]:
    codes = {code.strip() for code in role_codes if code.strip()}
    if not codes:
        raise NoRoleSelected()
    roles = list(db.scalars(select(Role).where(Role.code.in_(codes))))
    if len(roles) != len(codes):
        raise UnknownRole()
    _check_role_combination(db, codes)
    return roles


def create_user(
    db: Session,
    *,
    actor: User | None,
    username: str,
    display_name: str,
    password: str,
    role_codes: list[str],
    customer_type: CustomerType = CustomerType.INTERNAL,
    must_change_password: bool = True,
) -> User:
    username = normalize_username(username)
    if get_by_username(db, username) is not None:
        raise UsernameTaken(username=username)
    validate_password(password)
    roles = _resolve_roles(db, role_codes)

    user = User(
        username=username,
        display_name=display_name.strip() or username,
        password_hash=hash_password(password),
        customer_type=customer_type,
        is_active=True,
        must_change_password=must_change_password,
    )
    user.user_roles = [
        UserRole(role=role, assigned_by=actor.id if actor else None) for role in roles
    ]
    db.add(user)
    db.flush()
    audit.record(
        db,
        actor=actor,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        after={
            "username": user.username,
            "display_name": user.display_name,
            "roles": sorted(role.code for role in roles),
            "customer_type": user.customer_type.value,
        },
    )
    db.commit()
    db.refresh(user)
    return user


def register(db: Session, *, username: str, display_name: str, password: str) -> User:
    """Self-registration (FR-US-09): always role `user`, only when enabled in settings."""
    if not settings_service.get_bool(db, "registration_enabled"):
        raise RegistrationDisabled()
    user = create_user(
        db,
        actor=None,
        username=username,
        display_name=display_name,
        password=password,
        role_codes=["user"],
        must_change_password=False,
    )
    audit.record(db, actor=user, action="user.registered", entity_type="user", entity_id=user.id)
    db.commit()
    return user


def set_roles(db: Session, *, actor: User, user: User, role_codes: list[str]) -> User:
    if actor.id == user.id:
        raise SelfRoleChange()
    roles = _resolve_roles(db, role_codes)
    before = user.role_codes
    user.user_roles = [UserRole(role=role, assigned_by=actor.id) for role in roles]
    db.flush()
    db.expire(user, ["roles"])
    audit.record(
        db,
        actor=actor,
        action="user.roles_changed",
        entity_type="user",
        entity_id=user.id,
        before={"roles": before},
        after={"roles": sorted(role.code for role in roles)},
    )
    db.commit()
    db.refresh(user)
    return user


def set_active(db: Session, *, actor: User, user: User, active: bool) -> User:
    if actor.id == user.id:
        raise SelfDeactivation()
    if user.is_active == active:
        return user
    user.is_active = active
    audit.record(
        db,
        actor=actor,
        action="user.activated" if active else "user.deactivated",
        entity_type="user",
        entity_id=user.id,
        before={"is_active": not active},
        after={"is_active": active},
    )
    db.commit()
    return user


def reset_password(db: Session, *, actor: User, user: User) -> str:
    """Set a temporary password the admin passes on; the user must change it at next login."""
    temporary = generate_temporary_password()
    user.password_hash = hash_password(temporary)
    user.must_change_password = True
    audit.record(
        db, actor=actor, action="user.password_reset", entity_type="user", entity_id=user.id
    )
    db.commit()
    return temporary


def change_own_password(
    db: Session, *, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise WrongCurrentPassword()
    validate_password(new_password)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    audit.record(
        db, actor=user, action="user.password_changed", entity_type="user", entity_id=user.id
    )
    db.commit()
