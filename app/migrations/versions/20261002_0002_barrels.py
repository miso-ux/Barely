"""barrels and barrel status history, no-delete triggers

Revision ID: 0002_barrels
Revises: 0001_initial
Create Date: 2026-10-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_barrels"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("in_stock", "on_loan", "damaged", "lost", "retired", "written_off")
# Domain tables whose rows are never deleted (BR-11, FR-US-06, FR-BA-05).
NO_DELETE_TABLES = ("users", "barrels", "barrel_status_history")


def upgrade() -> None:
    barrel_status = sa.Enum(*STATUSES, name="barrel_status")
    barrel_status_ref = postgresql.ENUM(*STATUSES, name="barrel_status", create_type=False)

    op.create_table(
        "barrels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("status", barrel_status, nullable=False),
        sa.Column("loan_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("written_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_barrels_status", "barrels", ["status"])

    op.create_table(
        "barrel_status_history",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("barrel_id", sa.Integer(), sa.ForeignKey("barrels.id"), nullable=False),
        sa.Column("from_status", barrel_status_ref, nullable=True),
        sa.Column("to_status", barrel_status_ref, nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("loan_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_barrel_status_history_barrel_id", "barrel_status_history", ["barrel_id"])

    # System-generated barrel codes (B-0001, B-0002, ...) come from a sequence so that
    # concurrent inserts never collide.
    op.execute("CREATE SEQUENCE barrel_code_seq START 1")

    op.execute(
        """
        CREATE FUNCTION reject_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'rows in % are never deleted', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in NO_DELETE_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_delete();"
        )


def downgrade() -> None:
    for table in NO_DELETE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_delete()")
    op.execute("DROP SEQUENCE IF EXISTS barrel_code_seq")
    op.drop_index("ix_barrel_status_history_barrel_id", table_name="barrel_status_history")
    op.drop_table("barrel_status_history")
    op.drop_index("ix_barrels_status", table_name="barrels")
    op.drop_table("barrels")
    sa.Enum(name="barrel_status").drop(op.get_bind(), checkfirst=True)
