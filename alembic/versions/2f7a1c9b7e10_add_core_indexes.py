"""add core indexes

Revision ID: 2f7a1c9b7e10
Revises: 8f2b5a3f7c9e
Create Date: 2025-08-12 00:00:00
"""
from alembic import op

revision = "2f7a1c9b7e10"
down_revision = "8f2b5a3f7c9e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_files_game_category", "files", ["game", "category"])
    op.create_index("ix_games_collection_id", "games", ["collection_id"])
    op.create_index("ix_games_location_id", "games", ["location_id"])
    op.create_index("ix_locations_parent_id", "locations", ["parent_id"])
    op.create_index("ix_game_platforms_platform_id", "game_platforms", ["platform_id"])
    op.create_index("ix_game_genres_genre_id", "game_genres", ["genre_id"])
    op.create_index("ix_game_modes_mode_id", "game_modes", ["mode_id"])
    op.create_index("ix_game_playerperspectives_perspective_id", "game_playerperspectives", ["perspective_id"])
    op.create_index("ix_game_tags_tag_id", "game_tags", ["tag_id"])
    op.create_index("ix_game_companies_company_id", "game_companies", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_game_companies_company_id", table_name="game_companies")
    op.drop_index("ix_game_tags_tag_id", table_name="game_tags")
    op.drop_index("ix_game_playerperspectives_perspective_id", table_name="game_playerperspectives")
    op.drop_index("ix_game_modes_mode_id", table_name="game_modes")
    op.drop_index("ix_game_genres_genre_id", table_name="game_genres")
    op.drop_index("ix_game_platforms_platform_id", table_name="game_platforms")
    op.drop_index("ix_locations_parent_id", table_name="locations")
    op.drop_index("ix_games_location_id", table_name="games")
    op.drop_index("ix_games_collection_id", table_name="games")
    op.drop_index("ix_files_game_category", table_name="files")
