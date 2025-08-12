"""add file category to files

Revision ID: a1b2c3d4e5f6
Revises: 35143694426c
Create Date: 2025-08-12 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "35143694426c"
branch_labels = None
depends_on = None

file_category_enum = sa.Enum(
    "audio_ost",
    "patch_update",
    "saves",
    "disc_image",
    "screenshots",
    "manuals_docs",
    "artwork_covers",
    "other",
    name="file_category",
)

def upgrade() -> None:
    bind = op.get_bind()

    file_category_enum.create(bind, checkfirst=True)

    op.add_column(
        "files",
        sa.Column("category", file_category_enum, nullable=True),
    )

    op.execute("UPDATE files SET category = 'other' WHERE category IS NULL")

    op.alter_column(
        "files",
        "category",
        existing_type=file_category_enum,
        nullable=False,
    )

def downgrade() -> None:
    bind = op.get_bind()

    op.drop_column("files", "category")

    file_category_enum.drop(bind, checkfirst=False)
