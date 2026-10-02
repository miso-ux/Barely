"""SQLAlchemy models. Import every model module here so Alembic sees all tables."""

from app.db import Base
from app.models.audit import AuditLog
from app.models.barrel import Barrel, BarrelStatus, BarrelStatusHistory
from app.models.order import (
    ExceptionRequest,
    ExceptionRequestStatus,
    Loan,
    LoanStatus,
    Notification,
    Order,
    OrderKind,
    OrderStatus,
)
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.setting import Setting
from app.models.user import CustomerType, User

__all__ = [
    "AuditLog",
    "Barrel",
    "BarrelStatus",
    "BarrelStatusHistory",
    "Base",
    "CustomerType",
    "ExceptionRequest",
    "ExceptionRequestStatus",
    "Loan",
    "LoanStatus",
    "Notification",
    "Order",
    "OrderKind",
    "OrderStatus",
    "Permission",
    "Role",
    "RolePermission",
    "Setting",
    "User",
    "UserRole",
]
