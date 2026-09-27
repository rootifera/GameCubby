"""API surface inventory.

This is deliberately an explicit contract: adding, removing, or changing an
application endpoint fails CI until its integration coverage is reviewed.
The behavioural checks for these operations live in the PostgreSQL suite.
"""

from gamecubby_api.main import app


APPLICATION_OPERATIONS = {
    "DELETE /app_config/{key}", "DELETE /games/{game_id}",
    "DELETE /games/{game_id}/files/{file_id}", "DELETE /locations/{location_id}",
    "DELETE /tags/{tag_id}", "DELETE /wishlist/{wishlist_id}", "GET /",
    "GET /admin/maintenance/status", "GET /app_config/", "GET /app_config/{key}",
    "GET /backup/", "GET /backup/list", "GET /collections/",
    "GET /collections/collection_lookup/{game_id}", "GET /collections/{collection_id}",
    "GET /company/", "GET /company/{company_id}", "GET /downloads/{file_id}",
    "GET /export/games/csv", "GET /export/games/excel", "GET /export/games/json",
    "GET /files/categories", "GET /files/sync-all/status", "GET /first_run/status",
    "GET /games/", "GET /games/refresh_all_metadata/status", "GET /games/{game_id}",
    "GET /games/{game_id}/files/", "GET /games/{game_id}/location_path", "GET /genres/",
    "GET /genres/{genre_id}", "GET /health", "GET /health/ready", "GET /igdb/game/{igdb_id}",
    "GET /igdb/search", "GET /igdb/tags/{tag_id}", "GET /locations/",
    "GET /locations/children/{parent_id}", "GET /locations/top", "GET /locations/{location_id}",
    "GET /locations/{location_id}/games", "GET /modes/", "GET /modes/{mode_id}",
    "GET /perspectives/", "GET /perspectives/{perspective_id}", "GET /platforms/",
    "GET /platforms/{platform_id}", "GET /search/advanced", "GET /search/basic",
    "GET /search/suggest/collections", "GET /search/suggest/companies",
    "GET /search/suggest/igdb_tags", "GET /search/suggest/modes", "GET /search/suggest/names",
    "GET /search/suggest/tags", "GET /stats/health", "GET /stats/health/cover",
    "GET /stats/health/location", "GET /stats/health/platform", "GET /stats/health/release_year",
    "GET /stats/health/tag", "GET /stats/overview", "GET /tags/", "GET /tags/{tag_id}",
    "GET /wishlist/", "GET /wishlist/{wishlist_id}", "PATCH /games/{game_id}/files/{file_id}/label",
    "POST /admin/maintenance/enter", "POST /admin/maintenance/exit", "POST /app_config/",
    "POST /auth/change-password", "POST /auth/login", "POST /backup/save",
    "POST /backup/sync-storage", "POST /company/sync", "POST /files/sync-all",
    "POST /files/sync-storage", "POST /first_run", "POST /games/",
    "POST /games/force_refresh_metadata", "POST /games/from_igdb",
    "POST /games/refresh_all_metadata", "POST /games/{game_id}/convert_to_custom",
    "POST /games/{game_id}/files/sync-files", "POST /games/{game_id}/files/upload",
    "POST /games/{game_id}/refresh_metadata", "POST /genres/sync", "POST /locations/",
    "POST /locations/migrate", "POST /modes/sync", "POST /perspectives/sync",
    "POST /stats/force_refresh", "POST /tags/", "POST /wishlist/", "POST /wishlist/from_igdb",
    "POST /wishlist/{wishlist_id}/purchase", "POST /wishlist/{wishlist_id}/resolve",
    "PUT /games/{game_id}", "PUT /locations/{location_id}/rename", "PUT /wishlist/{wishlist_id}",
}


def test_application_operation_inventory_is_complete():
    actual = {
        f"{method} {route.path}"
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
        and route.path not in {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
    }
    assert actual == APPLICATION_OPERATIONS
