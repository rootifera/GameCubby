"""add s3 file metadata

Revision ID: 9d1f6a22b7c4
Revises: 8f2b5a3f7c9e
Create Date: 2026-06-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "9d1f6a22b7c4"
down_revision = "2f7a1c9b7e10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("storage_backend", sa.String(length=20), nullable=True, server_default="local"),
    )
    op.add_column("files", sa.Column("object_key", sa.String(length=1024), nullable=True))
    op.add_column("files", sa.Column("size", sa.BigInteger(), nullable=True))
    op.add_column("files", sa.Column("content_type", sa.String(length=255), nullable=True))

    op.execute("UPDATE files SET storage_backend = 'local' WHERE storage_backend IS NULL")
    op.alter_column("files", "storage_backend", nullable=False)


def downgrade() -> None:
    op.drop_column("files", "content_type")
    op.drop_column("files", "size")
    op.drop_column("files", "object_key")
    op.drop_column("files", "storage_backend")
