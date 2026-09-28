"""add cover_cached to games

Revision ID: e3b7c2a1f048
Revises: d8f5a1b3e920
Create Date: 2026-09-28 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "e3b7c2a1f048"
down_revision = "d8f5a1b3e920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games",
        sa.Column("cover_cached", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("games", "cover_cached")
