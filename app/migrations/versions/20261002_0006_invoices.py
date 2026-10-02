"""invoices, invoice items, gapless number sequence

Revision ID: 0006_invoices
Revises: 0005_pumps
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_invoices"
down_revision: str | None = "0005_pumps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NO_DELETE_TABLES = ("invoices", "invoice_items")


def _ts(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def _user_fk(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), sa.ForeignKey("users.id"), nullable=True)


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("number", sa.String(length=30), nullable=True),
        sa.Column("kind", sa.Enum("invoice", "credit_note", name="invoice_kind"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "issued", "sent", "cancelled", name="invoice_status"),
            nullable=False,
        ),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        _user_fk("created_by"),
        _ts("issued_at"),
        _user_fk("issued_by"),
        _ts("sent_at"),
        _user_fk("sent_by"),
        _ts("cancelled_at"),
        _user_fk("cancelled_by"),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("cancels_invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        _ts("paid_at"),
        _user_fk("paid_by"),
        sa.Column("payment_note", sa.Text(), nullable=True),
        sa.UniqueConstraint("number"),
    )
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column(
            "item_type",
            sa.Enum("penalty", "pump_order", "loan", name="invoice_item_type"),
            nullable=False,
        ),
        sa.Column("ref_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("released", sa.Boolean(), server_default="false", nullable=False),
        _ts("removed_at"),
    )
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])
    op.create_index(
        "uq_invoice_items_active_ref",
        "invoice_items",
        ["item_type", "ref_id"],
        unique=True,
        postgresql_where=sa.text("released = false"),
    )

    op.create_table(
        "invoice_number_sequence",
        sa.Column("year", sa.Integer(), primary_key=True),
        sa.Column("last_number", sa.Integer(), nullable=False),
    )

    for table in NO_DELETE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_delete();"
        )


def downgrade() -> None:
    for table in NO_DELETE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    op.drop_table("invoice_number_sequence")
    op.drop_table("invoice_items")
    op.drop_table("invoices")
    for name in ("invoice_item_type", "invoice_status", "invoice_kind"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
