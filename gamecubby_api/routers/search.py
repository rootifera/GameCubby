from fastapi import APIRouter, Request
from ..utils.search import (
    search_games_basic,
    search_game_name_suggestions,
    search_tag_suggestions,
    search_games_advanced,
    search_company_suggestions,
    search_collection_suggestions,
    search_mode_suggestions,
    search_igdb_tag_suggestions,
)

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "/basic",
    openapi_extra={
        "parameters": [
            {
                "name": "name",
                "in": "query",
                "required": False,
                "schema": {"type": "string"},
                "description": "Partial or full game name",
            },
            {
                "name": "year",
                "in": "query",
                "required": False,
                "schema": {"type": "integer"},
                "description": "Exact release year",
            },
            {
                "name": "platform_id",
                "in": "query",
                "required": False,
                "schema": {"type": "integer"},
                "description": "Platform ID (exact match)",
            },
            {
                "name": "tag_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more tag IDs to match",
            },
            {
                "name": "match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Tag match mode for tag_ids: 'any' (default), 'all' (must include all), or 'exact' (must include all and no others)",
            },
            {
                "name": "limit",
                "in": "query",
                "required": False,
                "schema": {"type": "integer"},
                "description": "Max number of results to return",
            },
            {
                "name": "offset",
                "in": "query",
                "required": False,
                "schema": {"type": "integer"},
                "description": "How many results to skip (for pagination)",
            },
        ]
    },
)
async def basic_search(request: Request):
    results = search_games_basic(request)
    return {"results": results}


@router.get(
    "/advanced",
    openapi_extra={
        "parameters": [
            {"name": "name", "in": "query", "required": False, "schema": {"type": "string"}},
            {"name": "year", "in": "query", "required": False, "schema": {"type": "integer"}},
            {"name": "year_min", "in": "query", "required": False, "schema": {"type": "integer"}},
            {"name": "year_max", "in": "query", "required": False, "schema": {"type": "integer"}},

            # Platforms + match mode
            {
                "name": "platform_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more platform IDs",
            },
            {
                "name": "platform_match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Match mode for platform_ids: 'any' (default), 'all', or 'exact'",
            },

            # User tags + match mode (keeps 'match_mode' for backward-compat)
            {
                "name": "tag_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more user tag IDs",
            },
            {
                "name": "match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Match mode for tag_ids (user tags): 'any' (default), 'all', or 'exact'",
            },

            # Genres + match mode
            {
                "name": "genre_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more genre IDs",
            },
            {
                "name": "genre_match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Match mode for genre_ids: 'any' (default), 'all', or 'exact'",
            },

            # Modes + match mode
            {
                "name": "mode_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more mode IDs",
            },
            {
                "name": "mode_match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Match mode for mode_ids: 'any' (default), 'all', or 'exact'",
            },

            # Perspectives + match mode
            {
                "name": "perspective_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more player perspective IDs",
            },
            {
                "name": "perspective_match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Match mode for perspective_ids: 'any' (default), 'all', or 'exact'",
            },

            # Collection
            {"name": "collection_id", "in": "query", "required": False, "schema": {"type": "integer"}},

            # Companies (single & multiple) + match mode
            {
                "name": "company_id",
                "in": "query",
                "required": False,
                "schema": {"type": "integer"},
                "description": "Company ID (you can repeat 'company_id' to pass multiple)",
            },
            {
                "name": "company_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more company IDs",
            },
            {
                "name": "company_match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Match mode for company_id/company_ids: 'any' (default), 'all', or 'exact'",
            },

            # IGDB tags + match mode
            {
                "name": "igdb_tag_ids",
                "in": "query",
                "required": False,
                "schema": {"type": "array", "items": {"type": "integer"}},
                "style": "form",
                "explode": True,
                "description": "One or more IGDB tag IDs",
            },
            {
                "name": "igdb_match_mode",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["any", "all", "exact"]},
                "description": "Match mode for igdb_tag_ids: 'any' (default), 'all', or 'exact'",
            },

            # Location
            {"name": "location_id", "in": "query", "required": False, "schema": {"type": "integer"}},
            {
                "name": "include_location_descendants",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["true", "false"]},
                "description": "If 'true', include games in all descendant locations of the given location_id. Default is 'false' (exact match only).",
            },

            # Manual entries toggles
            {
                "name": "include_manual",
                "in": "query",
                "required": False,
                "schema": {"type": "string", "enum": ["true", "false", "only"]},
                "description": "'true' = include manual entries, 'false' = exclude them, 'only' = only manual entries (igdb_id == 0).",
            },

            # Pagination
            {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
            {"name": "offset", "in": "query", "required": False, "schema": {"type": "integer"}},
        ]
    },
)
def advanced_search(request: Request):
    results = search_games_advanced(request)
    return {"results": results}


@router.get(
    "/suggest/names",
    openapi_extra={
        "parameters": [
            {
                "name": "q",
                "in": "query",
                "required": True,
                "schema": {"type": "string"},
                "description": "Partial game name to autocomplete",
            }
        ]
    },
)
def suggest_game_names(request: Request):
    suggestions = search_game_name_suggestions(request)
    return {"suggestions": suggestions}


@router.get(
    "/suggest/tags",
    openapi_extra={
        "parameters": [
            {
                "name": "q",
                "in": "query",
                "required": True,
                "schema": {"type": "string"},
                "description": "Partial tag name to autocomplete",
            }
        ]
    },
)
def suggest_tags(request: Request):
    suggestions = search_tag_suggestions(request)
    return {"suggestions": suggestions}


@router.get(
    "/suggest/igdb_tags",
    openapi_extra={
        "parameters": [
            {
                "name": "q",
                "in": "query",
                "required": True,
                "schema": {"type": "string"},
                "description": "Partial IGDB tag name",
            }
        ]
    },
)
def suggest_igdb_tags(request: Request):
    suggestions = search_igdb_tag_suggestions(request)
    return {"suggestions": suggestions}


@router.get(
    "/suggest/modes",
    openapi_extra={
        "parameters": [
            {
                "name": "q",
                "in": "query",
                "required": True,
                "schema": {"type": "string"},
                "description": "Partial mode name",
            }
        ]
    },
)
def suggest_modes(request: Request):
    suggestions = search_mode_suggestions(request)
    return {"suggestions": suggestions}


@router.get(
    "/suggest/collections",
    openapi_extra={
        "parameters": [
            {
                "name": "q",
                "in": "query",
                "required": True,
                "schema": {"type": "string"},
                "description": "Partial collection name",
            }
        ]
    },
)
def suggest_collections(request: Request):
    suggestions = search_collection_suggestions(request)
    return {"suggestions": suggestions}


@router.get(
    "/suggest/companies",
    openapi_extra={
        "parameters": [
            {
                "name": "q",
                "in": "query",
                "required": True,
                "schema": {"type": "string"},
                "description": "Partial company name",
            }
        ]
    },
)
def suggest_companies(request: Request):
    suggestions = search_company_suggestions(request)
    return {"suggestions": suggestions}
