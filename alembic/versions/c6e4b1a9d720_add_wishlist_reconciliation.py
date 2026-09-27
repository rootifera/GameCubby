"""add wishlist reconciliation

Revision ID: c6e4b1a9d720
Revises: a4c8e2d9f601
Create Date: 2026-09-27 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "c6e4b1a9d720"
down_revision = "a4c8e2d9f601"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wishlist_items",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column("wishlist_items", sa.Column("library_game_id", sa.Integer(), nullable=True))
    op.create_index("ix_wishlist_items_status", "wishlist_items", ["status"])
    op.create_foreign_key(
        "fk_wishlist_items_library_game_id_games",
        "wishlist_items",
        "games",
        ["library_game_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_wishlist_items_library_game_id_games", "wishlist_items", type_="foreignkey")
    op.drop_index("ix_wishlist_items_status", table_name="wishlist_items")
    op.drop_column("wishlist_items", "library_game_id")
    op.drop_column("wishlist_items", "status")
