"""pump products, stock movements, pump fields on orders

Revision ID: 0005_pumps
Revises: 0004_penalties
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_pumps"
down_revision: str | None = "0004_penalties"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NO_DELETE_TABLES = ("pump_products", "pump_stock_movements")


def upgrade() -> None:
    op.create_table(
        "pump_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("stock", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "pump_stock_movements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("pump_products.id"), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_pump_stock_movements_product_id", "pump_stock_movements", ["product_id"])

    op.add_column(
        "orders",
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("pump_products.id"), nullable=True),
    )
    op.add_column("orders", sa.Column("unit_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("orders", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "orders", sa.Column("paid_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True)
    )
    op.add_column("orders", sa.Column("payment_note", sa.Text(), nullable=True))

    for table in NO_DELETE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_delete();"
        )


def downgrade() -> None:
    for table in NO_DELETE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    for column in ("payment_note", "paid_by", "paid_at", "unit_price", "product_id"):
        op.drop_column("orders", column)
    op.drop_index("ix_pump_stock_movements_product_id", table_name="pump_stock_movements")
    op.drop_table("pump_stock_movements")
    op.drop_table("pump_products")
