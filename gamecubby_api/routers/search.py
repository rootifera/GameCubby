from fastapi import APIRouter, Request
from ..utils.search import search_games_basic, search_game_name_suggestions, search_tag_suggestions, \
    search_games_advanced, search_company_suggestions, search_collection_suggestions, search_mode_suggestions, \
    search_igdb_tag_suggestions

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("/basic", openapi_extra={
    "parameters": [
        {
            "name": "name",
            "in": "query",
            "required": False,
            "schema": {"type": "string"},
            "description": "Partial or full game name"
        },
        {
            "name": "year",
            "in": "query",
            "required": False,
            "schema": {"type": "integer"},
            "description": "Exact release year"
        },
        {
            "name": "platform_id",
            "in": "query",
            "required": False,
            "schema": {"type": "integer"},
            "description": "Platform ID (exact match)"
        },
        {
            "name": "tag_ids",
            "in": "query",
            "required": False,
            "schema": {
                "type": "array",
                "items": {"type": "integer"}
            },
            "style": "form",
            "explode": True,
            "description": "One or more tag IDs to match"
        },
        {
            "name": "match_mode",
            "in": "query",
            "required": False,
            "schema": {"type": "string", "enum": ["any", "all"]},
            "description": "Tag match mode: 'any' (default) or 'all'"
        },
        {
            "name": "limit",
            "in": "query",
            "required": False,
            "schema": {"type": "integer"},
            "description": "Max number of results to return"
        },
        {
            "name": "offset",
            "in": "query",
            "required": False,
            "schema": {"type": "integer"},
            "description": "How many results to skip (for pagination)"
        }
    ]
})
def basic_search(request: Request):
    return search_games_basic(request)


@router.get("/advanced", openapi_extra={
    "parameters": [
        {"name": "name", "in": "query", "required": False, "schema": {"type": "string"}},
        {"name": "year", "in": "query", "required": False, "schema": {"type": "integer"}},
        {"name": "year_min", "in": "query", "required": False, "schema": {"type": "integer"}},
        {"name": "year_max", "in": "query", "required": False, "schema": {"type": "integer"}},
        {"name": "platform_ids", "in": "query", "required": False,
         "schema": {"type": "array", "items": {"type": "integer"}}, "style": "form", "explode": True},
        {"name": "tag_ids", "in": "query", "required": False, "schema": {"type": "array", "items": {"type": "integer"}},
         "style": "form", "explode": True},
        {"name": "genre_ids", "in": "query", "required": False,
         "schema": {"type": "array", "items": {"type": "integer"}}, "style": "form", "explode": True},
        {"name": "mode_ids", "in": "query", "required": False,
         "schema": {"type": "array", "items": {"type": "integer"}}, "style": "form", "explode": True},
        {"name": "perspective_ids", "in": "query", "required": False,
         "schema": {"type": "array", "items": {"type": "integer"}}, "style": "form", "explode": True},
        {"name": "collection_id", "in": "query", "required": False, "schema": {"type": "integer"}},
        {"name": "company_id", "in": "query", "required": False, "schema": {"type": "integer"}},
        {"name": "igdb_tag_ids", "in": "query", "required": False,
         "schema": {"type": "array", "items": {"type": "integer"}}, "style": "form", "explode": True},
        {"name": "location_id", "in": "query", "required": False, "schema": {"type": "integer"}},
        {"name": "include_manual", "in": "query", "required": False,
         "schema": {"type": "string", "enum": ["true", "false", "only"]}},
        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
        {"name": "offset", "in": "query", "required": False, "schema": {"type": "integer"}}
    ]
})
def advanced_search(request: Request):
    return search_games_advanced(request)


@router.get("/suggest/names", openapi_extra={
    "parameters": [
        {
            "name": "q",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Partial game name to autocomplete"
        }
    ]
})
def suggest_game_names(request: Request):
    return search_game_name_suggestions(request)


@router.get("/suggest/tags", openapi_extra={
    "parameters": [
        {
            "name": "q",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Partial tag name to autocomplete"
        }
    ]
})
def suggest_tags(request: Request):
    return search_tag_suggestions(request)


@router.get("/suggest/igdb_tags", openapi_extra={
    "parameters": [
        {
            "name": "q",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Partial IGDB tag name"
        }
    ]
})
def suggest_igdb_tags(request: Request):
    return search_igdb_tag_suggestions(request)


@router.get("/suggest/modes", openapi_extra={
    "parameters": [
        {
            "name": "q",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Partial mode name"
        }
    ]
})
def suggest_modes(request: Request):
    return search_mode_suggestions(request)


@router.get("/suggest/collections", openapi_extra={
    "parameters": [
        {
            "name": "q",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Partial collection name"
        }
    ]
})
def suggest_collections(request: Request):
    return search_collection_suggestions(request)


@router.get("/suggest/companies", openapi_extra={
    "parameters": [
        {
            "name": "q",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Partial company name"
        }
    ]
})
def suggest_companies(request: Request):
    return search_company_suggestions(request)
