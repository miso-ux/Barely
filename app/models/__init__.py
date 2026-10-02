"""SQLAlchemy models. Import every model module here so Alembic sees all tables."""

from app.db import Base
from app.models.audit import AuditLog
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.setting import Setting
from app.models.user import CustomerType, User

__all__ = [
    "AuditLog",
    "Base",
    "CustomerType",
    "Permission",
    "Role",
    "RolePermission",
    "Setting",
    "User",
    "UserRole",
]
