"""add wishlist

Revision ID: a4c8e2d9f601
Revises: 9d1f6a22b7c4
Create Date: 2026-09-26 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "a4c8e2d9f601"
down_revision = "9d1f6a22b7c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wishlist_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("igdb_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("release_year", sa.Integer(), nullable=True),
        sa.Column("cover_url", sa.String(), nullable=True),
    )
    op.create_index("ix_wishlist_items_igdb_id", "wishlist_items", ["igdb_id"])
    op.create_table(
        "wishlist_platforms",
        sa.Column("wishlist_id", sa.Integer(), sa.ForeignKey("wishlist_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("platform_id", sa.Integer(), sa.ForeignKey("platforms.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "wishlist_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wishlist_item_id", sa.Integer(), sa.ForeignKey("wishlist_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
    )
    op.create_index("ix_wishlist_links_wishlist_item_id", "wishlist_links", ["wishlist_item_id"])


def downgrade() -> None:
    op.drop_index("ix_wishlist_links_wishlist_item_id", table_name="wishlist_links")
    op.drop_table("wishlist_links")
    op.drop_table("wishlist_platforms")
    op.drop_index("ix_wishlist_items_igdb_id", table_name="wishlist_items")
    op.drop_table("wishlist_items")
