"""add purchase link shortcuts

Revision ID: d8f5a1b3e920
Revises: c6e4b1a9d720
Create Date: 2026-09-27 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "d8f5a1b3e920"
down_revision = "c6e4b1a9d720"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_link_shortcuts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "uq_purchase_link_shortcuts_label_normalized",
        "purchase_link_shortcuts",
        [sa.text("lower(btrim(label))")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_purchase_link_shortcuts_label_normalized", table_name="purchase_link_shortcuts")
    op.drop_table("purchase_link_shortcuts")
