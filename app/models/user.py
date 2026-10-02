import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.rbac import Role, UserRole


class CustomerType(enum.StrEnum):
    """Customers are not assumed to be employees (NFR-10)."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    customer_type: Mapped[CustomerType] = mapped_column(
        Enum(CustomerType, name="customer_type", values_callable=lambda e: [m.value for m in e]),
        default=CustomerType.INTERNAL,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Optional billing details, only relevant for external customers (FR-EX-02).
    billing_name: Mapped[str | None] = mapped_column(String(200))
    billing_company_id: Mapped[str | None] = mapped_column(String(50))
    billing_tax_id: Mapped[str | None] = mapped_column(String(50))
    billing_address: Mapped[str | None] = mapped_column(String(500))

    # user_roles has two FKs to users (user_id, assigned_by), so the join must be explicit.
    roles: Mapped[list[Role]] = relationship(
        secondary="user_roles",
        primaryjoin="User.id == UserRole.user_id",
        secondaryjoin="Role.id == UserRole.role_id",
        viewonly=True,
        lazy="selectin",
    )
    user_roles: Mapped[list[UserRole]] = relationship(
        foreign_keys="UserRole.user_id", cascade="all, delete-orphan"
    )

    @property
    def role_codes(self) -> list[str]:
        return sorted(role.code for role in self.roles)

    @property
    def permission_codes(self) -> frozenset[str]:
        return frozenset(perm.code for role in self.roles for perm in role.permissions)

    def has_permission(self, code: str) -> bool:
        return code in self.permission_codes

    def has_any_permission(self, *codes: str) -> bool:
        return any(code in self.permission_codes for code in codes)
