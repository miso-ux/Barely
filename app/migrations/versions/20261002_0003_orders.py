"""orders, exception requests, loans, notifications

Revision ID: 0003_orders
Revises: 0002_barrels
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_orders"
down_revision: str | None = "0002_barrels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NO_DELETE_TABLES = ("orders", "exception_requests", "loans", "notifications")


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id"), nullable=True)


def upgrade() -> None:
    order_kind = sa.Enum("barrel", "pump", name="order_kind")
    order_status = sa.Enum("pending", "ready", "issued", "closed", "cancelled", name="order_status")
    exception_status = sa.Enum("pending", "approved", "rejected", name="exception_request_status")
    loan_status = sa.Enum(
        "on_loan", "returned", "returned_damaged", "overdue", "lost", name="loan_status"
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", order_kind, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("requested_date", sa.Date(), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _user_fk("created_by"),
        _ts("ready_at"),
        _user_fk("ready_by"),
        _ts("issued_at"),
        _user_fk("issued_by"),
        _ts("closed_at"),
        _ts("cancelled_at"),
        _user_fk("cancelled_by"),
        sa.Column("cancel_reason", sa.String(length=50), nullable=True),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_requested_date", "orders", ["requested_date"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "exception_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("requested_date", sa.Date(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("status", exception_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _user_fk("decided_by"),
        _ts("decided_at"),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
    )
    op.create_index("ix_exception_requests_user_id", "exception_requests", ["user_id"])
    op.create_index("ix_exception_requests_status", "exception_requests", ["status"])

    op.create_table(
        "loans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("barrel_id", sa.Integer(), sa.ForeignKey("barrels.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("loan_sequence", sa.Integer(), nullable=False),
        _ts("issued_at", nullable=False),
        _user_fk("issued_by"),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("loan_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", loan_status, nullable=False),
        _ts("returned_at"),
        _user_fk("returned_by"),
        sa.Column("return_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_loans_order_id", "loans", ["order_id"])
    op.create_index("ix_loans_barrel_id", "loans", ["barrel_id"])
    op.create_index("ix_loans_user_id", "loans", ["user_id"])
    op.create_index("ix_loans_due_date", "loans", ["due_date"])
    op.create_index("ix_loans_status", "loans", ["status"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("link", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _ts("read_at"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    # Barrel history can now point at the loan that caused the change.
    op.create_foreign_key(
        "fk_barrel_status_history_loan_id_loans",
        "barrel_status_history",
        "loans",
        ["loan_id"],
        ["id"],
    )

    for table in NO_DELETE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_delete();"
        )


def downgrade() -> None:
    for table in NO_DELETE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    op.drop_constraint(
        "fk_barrel_status_history_loan_id_loans", "barrel_status_history", type_="foreignkey"
    )
    op.drop_table("notifications")
    op.drop_table("loans")
    op.drop_table("exception_requests")
    op.drop_table("orders")
    for name in ("loan_status", "exception_request_status", "order_status", "order_kind"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
