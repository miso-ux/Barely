"""penalties, loan reminder timestamp

Revision ID: 0004_penalties
Revises: 0003_orders
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_penalties"
down_revision: str | None = "0003_orders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("loans", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "penalties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("loan_id", sa.Integer(), sa.ForeignKey("loans.id"), nullable=False),
        sa.Column("barrel_id", sa.Integer(), sa.ForeignKey("barrels.id"), nullable=False),
        sa.Column(
            "reason", sa.Enum("overdue", "damaged", "lost", name="penalty_reason"), nullable=False
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "status",
            sa.Enum("unpaid", "paid", "cancelled", name="penalty_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("payment_note", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_penalties_user_id", "penalties", ["user_id"])
    op.create_index("ix_penalties_loan_id", "penalties", ["loan_id"])
    op.create_index("ix_penalties_status", "penalties", ["status"])
    op.create_index(
        "uq_penalties_loan_reason_active",
        "penalties",
        ["loan_id", "reason"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.execute(
        "CREATE TRIGGER penalties_no_delete BEFORE DELETE ON penalties "
        "FOR EACH ROW EXECUTE FUNCTION reject_delete();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS penalties_no_delete ON penalties")
    op.drop_table("penalties")
    for name in ("penalty_status", "penalty_reason"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
    op.drop_column("loans", "reminder_sent_at")
