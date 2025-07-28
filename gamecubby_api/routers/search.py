from fastapi import APIRouter, Request
from ..utils.search import search_games_basic, search_game_name_suggestions, search_tag_suggestions

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