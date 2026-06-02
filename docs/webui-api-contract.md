# WebUI API Contract Map

This document tracks the API behavior currently consumed by `GameCubby-Web`.
Use it as a safety checklist before refactoring API endpoints. The API can be
cleaned internally, but these externally visible paths, request shapes, auth
expectations, and response fields should not change unless the WebUI is changed
in the same work.

Source snapshot:

- API repo: `GameCubby`, branch `refactor`
- WebUI repo: `GameCubby-Web`, branch `refactor`
- API contract source: generated `openapi.json` in the API repo
- WebUI source: `src/app`, `src/components`, `src/lib`

## Rules

- Treat the API repo's generated OpenAPI as the endpoint/path/method contract.
- Treat the WebUI code as the consumed-field contract.
- Preserve public endpoints that the WebUI calls without a bearer token.
- Preserve query/body shapes even when they look unusual.
- Preserve response JSON keys used by WebUI TypeScript types and rendering code.
- Add integration smoke coverage before changing any endpoint behavior.

## Public Startup And Health

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `GET /first_run/status` | Home redirect/setup checks and `/api/health` | Returns boolean. Must remain public. |
| `POST /first_run` | `src/app/setup/submit/route.ts` | Public first setup. Expects JSON including admin credentials and app settings. |
| `GET /health` | API status/proxy health | Used as availability signal. |
| `GET /` | Admin overview | Returns API metadata/version fields consumed by admin dashboard. |

## Public Browsing

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `GET /games/` | Games list, admin pickers, proxies | Public. List items need preview fields such as `id`, `name`, `cover_url`, `release_year`, `platforms`, `location`, tags/order fields where present. |
| `GET /games/{game_id}` | Game detail, hover card, update/delete pages | Public. Detail shape is heavily consumed; preserve nested location, platform, genre, mode, perspective, tag, IGDB tag, company, collection, file-related fields. |
| `GET /games/{game_id}/files/` | Game detail and file manager | Public/admin-with-token compatible. File rows need stable `file_id` or `id`, `label`, `filename`, `category`, `size`, and download-related fields. |
| `GET /downloads/{file_id}` | Download proxy | Public only when app config allows; bearer token should continue to allow admin downloads. |
| `GET /platforms/` | Search filters and admin forms | Public lookup, no bearer expected. |
| `GET /genres/` | Advanced search filters | Public lookup, no bearer expected. |
| `GET /perspectives/` | Advanced search filters | Public lookup, no bearer expected. |
| `GET /modes/` | Advanced search filters and suggestions | Public lookup, no bearer expected. |
| `GET /collections/` | Advanced search filters and suggestions | Public lookup, no bearer expected. |
| `GET /company/` | Advanced search filters and suggestions | Public lookup, no bearer expected. |
| `GET /tags/` | Suggestions and admin tag creation flow | Public list and query-by-name behavior are both used. |
| `GET /tags/{tag_id}` | Tag autocomplete chips | Public lookup by id. |
| `GET /igdb/tags/{tag_id}` | IGDB tag autocomplete chips | Public lookup by id. |

## Search

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `GET /search/basic` | Basic search page and proxy | Query params are forwarded from WebUI. Preserve modes like name/tag/platform/location where currently accepted. |
| `GET /search/advanced` | Advanced search page and proxy | Query params are forwarded from WebUI. Preserve `sort_by_order` handling and current result shape. |
| `GET /search/suggest/names` | Search box autocomplete | Returns string array. |
| `GET /search/suggest/tags` | Tag suggestions | Returns suggestion array consumed by chip/autocomplete UI. |
| `GET /search/suggest/igdb_tags` | IGDB tag suggestions | Returns suggestion array consumed by chip/autocomplete UI. |
| `GET /search/suggest/modes` | Admin lookup suggestions | Public. |
| `GET /search/suggest/collections` | Admin lookup suggestions | Public. |
| `GET /search/suggest/companies` | Admin lookup suggestions | Public. |

## Stats

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `GET /stats/overview` | Home dashboard | Preserve count and recent/missing summary keys used by home page. |
| `GET /stats/health` | Home dashboard | Preserve aggregate health keys. |
| `GET /stats/health/cover` | Health drilldown | Returns object with `ids`. |
| `GET /stats/health/release_year` | Health drilldown | Returns object with `ids`. |
| `GET /stats/health/platform` | Health drilldown | Returns object with `ids`. |
| `GET /stats/health/location` | Health drilldown | Returns object with `ids`. |
| `GET /stats/health/tag` | Health drilldown | Returns object with `ids`. |
| `POST /stats/force_refresh` | Force refresh button | Requires admin bearer. |

## Auth And Settings

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `POST /auth/login` | Admin login route | Expects username/password form converted to API login request. Response must include access token field used for cookie. |
| `POST /auth/change-password` | Admin settings password form | Requires bearer. Body is forwarded as JSON. |
| `GET /app_config/` | Admin application settings | Requires bearer. Returns array of `{ key, value }`. |
| `POST /app_config/` | Admin application settings | Requires bearer. Expects `{ key, value }`, returns saved entry. |

## Admin Games

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `POST /games/` | Manual add game | Requires bearer. JSON body is forwarded from WebUI. |
| `PUT /games/{game_id}` | Update game | Requires bearer. JSON body is forwarded from WebUI. WebUI proxies may try with and without trailing slash. |
| `DELETE /games/{game_id}` | Delete game | Requires bearer. Returns current API delete response. |
| `POST /games/from_igdb` | Add from IGDB | Requires bearer. JSON body is passed through as-is. |
| `POST /games/{game_id}/refresh_metadata` | Per-game sync | Requires bearer. WebUI expects JSON status/message style response. |
| `POST /games/refresh_all_metadata` | Bulk sync | Requires bearer. WebUI expects JSON status/detail style response. |
| `POST /games/force_refresh_metadata` | Force metadata refresh | Requires bearer. WebUI expects JSON status/detail style response. |
| `GET /igdb/search` | Add from IGDB search | Public per current WebUI proxy; no bearer is sent. |
| `GET /igdb/game/{igdb_id}` | Add from IGDB details | Requires bearer. |

## Files

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `POST /games/{game_id}/files/upload` | File manager upload | Requires bearer. Multipart body is streamed through. |
| `DELETE /games/{game_id}/files/{file_id}` | File manager delete | Requires bearer. |
| `PATCH /games/{game_id}/files/{file_id}/label` | File manager label edit | Requires bearer. JSON body is forwarded. |
| `POST /games/{game_id}/files/sync-files` | Per-game file sync | Requires bearer. |
| `POST /files/sync-all` | Global file sync | Requires bearer. |

## Locations

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `GET /locations/` | Location manager | Public. |
| `GET /locations/top` | Location picker | Public. |
| `GET /locations/children/{parent_id}` | Location tree expansion | Public. |
| `GET /locations/{location_id}` | Location manager and picker | Public. |
| `GET /locations/{location_id}/games` | Add game order picker and migrate tool | Public. Returns `id`/`name` list. |
| `POST /locations/` | Location manager create | Requires bearer. Upstream API expects query params, not JSON body. Preserve this. |
| `PUT /locations/{location_id}/rename` | Location manager rename | Requires bearer. JSON body is passed through. |
| `DELETE /locations/{location_id}` | Location manager delete | Requires bearer. |
| `POST /locations/migrate` | Bulk location change | Requires bearer. JSON body is forwarded. |

## Export, Backup, Maintenance

| API endpoint | WebUI usage | Contract notes |
| --- | --- | --- |
| `GET /export/games/json` | Admin export | Requires bearer. |
| `GET /export/games/csv` | Admin export | Requires bearer. |
| `GET /export/games/excel` | Admin export | Requires bearer. |
| `GET /backup/` | Admin backup download | Requires bearer. |
| `POST /backup/save` | Sentinel backup flow may use local WebUI route | Requires bearer if called directly. |
| `GET /admin/maintenance/status` | Restore/maintenance flow | WebUI middleware depends on maintenance state behavior. |
| `POST /admin/maintenance/enter` | Restore/maintenance flow | Must remain callable by restore flow. |
| `POST /admin/maintenance/exit` | Restore/maintenance flow | Must remain callable by restore flow. |

## Endpoints Not Currently Frontend-Primary

These are in the API OpenAPI contract and should remain smoke-tested, but they
do not appear to be central WebUI dependencies from the current static scan:

- `GET /platforms/{platform_id}`
- `GET /genres/{genre_id}`
- `POST /genres/sync`
- `GET /modes/{mode_id}`
- `POST /modes/sync`
- `GET /perspectives/{perspective_id}`
- `POST /perspectives/sync`
- `GET /collections/{collection_id}`
- `GET /collections/collection_lookup/{game_id}`
- `GET /company/{company_id}`
- `POST /company/sync`
- `GET /files/categories`
- `GET /games/{game_id}/location_path`
- `DELETE /app_config/{key}`
- `DELETE /tags/{tag_id}`

## Safe Refactor Workflow

1. Pick one API area.
2. Check this map and the WebUI files named by the relevant section.
3. Add or confirm smoke coverage for the exact WebUI request/response shape.
4. Make the smallest API change that preserves the contract.
5. Regenerate and compare OpenAPI.
6. Run the integration smoke suite.
7. If touching a WebUI-consumed route, run or add a WebUI-aware smoke step.
