"""SQLAlchemy models. Import every model module here so Alembic sees all tables."""

from app.db import Base
from app.models.audit import AuditLog
from app.models.barrel import Barrel, BarrelStatus, BarrelStatusHistory
from app.models.invoice import (
    ACTIVE_INVOICE_STATUSES,
    Invoice,
    InvoiceItem,
    InvoiceItemType,
    InvoiceKind,
    InvoiceNumberSequence,
    InvoiceStatus,
)
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
from app.models.penalty import Penalty, PenaltyReason, PenaltyStatus
from app.models.pump import MovementReason, PumpProduct, PumpStockMovement
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.setting import Setting
from app.models.user import CustomerType, User

__all__ = [
    "ACTIVE_INVOICE_STATUSES",
    "AuditLog",
    "Invoice",
    "InvoiceItem",
    "InvoiceItemType",
    "InvoiceKind",
    "InvoiceNumberSequence",
    "InvoiceStatus",
    "Barrel",
    "BarrelStatus",
    "BarrelStatusHistory",
    "Base",
    "CustomerType",
    "ExceptionRequest",
    "ExceptionRequestStatus",
    "Loan",
    "LoanStatus",
    "MovementReason",
    "PumpProduct",
    "PumpStockMovement",
    "Notification",
    "Order",
    "OrderKind",
    "OrderStatus",
    "Penalty",
    "PenaltyReason",
    "PenaltyStatus",
    "Permission",
    "Role",
    "RolePermission",
    "Setting",
    "User",
    "UserRole",
]
