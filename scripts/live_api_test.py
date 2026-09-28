#!/usr/bin/env python3
"""
Comprehensive live API test against a running GameCubby instance.
Usage: python3 scripts/live_api_test.py [base_url]
Default base_url: http://localhost:8000
"""

import sys
import json
import time
import requests

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
USERNAME = "rootifera"
PASSWORD = "admin123"

PASS = "\033[92m PASS\033[0m"
FAIL = "\033[91m FAIL\033[0m"
SKIP = "\033[93m SKIP\033[0m"

passes = []
failures = []

def check(label, condition, detail=""):
    if condition:
        print(f"{PASS} {label}")
        passes.append(label)
    else:
        print(f"{FAIL} {label}" + (f" — {detail}" if detail else ""))
        failures.append(label)

def section(title):
    print(f"\n── {title} {'─' * max(0, 60 - len(title))}")

s = requests.Session()
token = None

def auth():
    return {"Authorization": f"Bearer {token}"} if token else {}

def get(path, **kw):    return s.get(BASE + path, **kw)
def post(path, **kw):   return s.post(BASE + path, **kw)
def put(path, **kw):    return s.put(BASE + path, **kw)
def patch(path, **kw):  return s.patch(BASE + path, **kw)
def delete(path, **kw): return s.delete(BASE + path, **kw)

# ── Health ────────────────────────────────────────────────────────────────────
section("Health")
r = get("/health")
check("GET /health returns 200 with ok=true", r.status_code == 200 and r.json().get("ok") is True)
r = get("/health/ready")
check("GET /health/ready returns 200 with database=available", r.status_code == 200 and r.json().get("database") == "available")
r = get("/")
check("GET / returns version info", r.status_code == 200 and "version" in r.json())

# ── Auth ─────────────────────────────────────────────────────────────────────
section("Auth")
r = post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
check("POST /auth/login with valid credentials returns 200", r.status_code == 200)
if r.status_code == 200:
    token = r.json().get("access_token")
    check("Login response contains access_token", bool(token))

r = post("/auth/login", json={"username": USERNAME, "password": "wrongpassword"})
check("POST /auth/login with wrong password returns 401", r.status_code == 401)

r = post("/auth/login", json={"username": "nonexistent", "password": "x"})
check("POST /auth/login with unknown user returns 401", r.status_code == 401)

# ── Setup / First run ────────────────────────────────────────────────────────
section("Setup")
r = get("/first_run/status")
check("GET /first_run/status returns bool", r.status_code == 200 and isinstance(r.json(), bool))

# ── App Config ───────────────────────────────────────────────────────────────
section("App Config")
r = get("/app_config/", headers=auth())
check("GET /app_config/ returns 200 (admin)", r.status_code == 200)

r = post("/app_config/", headers=auth(), json={"key": "live_test_key", "value": "live_test_value"})
check("POST /app_config/ creates key", r.status_code == 200)

r = get("/app_config/live_test_key", headers=auth())
check("GET /app_config/{key} returns value", r.status_code == 200 and r.json().get("value") == "live_test_value")

r = delete("/app_config/live_test_key", headers=auth())
check("DELETE /app_config/{key} removes key", r.status_code == 200)

r = get("/app_config/live_test_key", headers=auth())
check("GET /app_config/{key} returns 404 after delete", r.status_code == 404)

r = get("/app_config/", )
check("GET /app_config/ returns 401 without auth", r.status_code in {401, 403})

# ── Platforms ────────────────────────────────────────────────────────────────
section("Platforms")
r = get("/platforms/")
check("GET /platforms/ returns list", r.status_code == 200 and isinstance(r.json(), list))
platforms = r.json()
if platforms:
    pid = platforms[0]["id"]
    r = get(f"/platforms/{pid}")
    check(f"GET /platforms/{{id}} returns platform", r.status_code == 200)

r = get("/platforms/999999")
check("GET /platforms/999999 returns 404", r.status_code == 404)

# ── Genres ───────────────────────────────────────────────────────────────────
section("Genres")
r = get("/genres/")
check("GET /genres/ returns list", r.status_code == 200 and isinstance(r.json(), list))
genres = r.json()
if genres:
    gid = genres[0]["id"]
    r = get(f"/genres/{gid}")
    check("GET /genres/{id} returns genre", r.status_code == 200)

# ── Modes ────────────────────────────────────────────────────────────────────
section("Modes")
r = get("/modes/")
check("GET /modes/ returns list", r.status_code == 200 and isinstance(r.json(), list))
modes = r.json()
if modes:
    mid = modes[0]["id"]
    r = get(f"/modes/{mid}")
    check("GET /modes/{id} returns mode", r.status_code == 200)

# ── Player Perspectives ───────────────────────────────────────────────────────
section("Player Perspectives")
r = get("/perspectives/")
check("GET /perspectives/ returns list", r.status_code == 200 and isinstance(r.json(), list))
perspectives = r.json()
if perspectives:
    ppid = perspectives[0]["id"]
    r = get(f"/perspectives/{ppid}")
    check("GET /perspectives/{id} returns perspective", r.status_code == 200)

# ── Companies ────────────────────────────────────────────────────────────────
section("Companies")
r = get("/company/")
check("GET /company/ returns list", r.status_code == 200 and isinstance(r.json(), list))

# ── Collections ──────────────────────────────────────────────────────────────
section("Collections")
r = get("/collections/")
check("GET /collections/ returns list", r.status_code == 200 and isinstance(r.json(), list))
collections_list = r.json()
coll_id = None
if collections_list:
    coll_id = collections_list[0]["id"]
    r2 = get(f"/collections/{coll_id}")
    check("GET /collections/{id} returns collection", r2.status_code == 200)
# Collections are created automatically via IGDB game import, no standalone POST endpoint.

# ── Tags ─────────────────────────────────────────────────────────────────────
section("Tags")
r = post("/tags/", headers=auth(), params={"name": "live-test-tag"})
check("POST /tags/ creates tag", r.status_code == 200)
tag_id = None
if r.status_code == 200:
    tag_id = r.json().get("id")
    r2 = get("/tags/")
    check("GET /tags/ returns list including new tag", r2.status_code == 200 and any(t["id"] == tag_id for t in r2.json()))
    r2 = get(f"/tags/{tag_id}")
    check("GET /tags/{id} returns tag", r2.status_code == 200)

# ── Locations ────────────────────────────────────────────────────────────────
section("Locations")
r = get("/locations/")
check("GET /locations/ returns list", r.status_code == 200)

r = get("/locations/top")
check("GET /locations/top returns root locations", r.status_code == 200)

r = post("/locations/", headers=auth(), params={"name": "Live Test Root", "type": "root"})
check("POST /locations/ creates root location", r.status_code == 200)
root_loc_id = None
child_loc_id = None
if r.status_code == 200:
    root_loc_id = r.json().get("id")
    r2 = post("/locations/", headers=auth(), params={"name": "Live Test Shelf", "type": "shelf", "parent_id": root_loc_id})
    check("POST /locations/ creates child shelf", r2.status_code == 200)
    if r2.status_code == 200:
        child_loc_id = r2.json().get("id")

    r2 = get(f"/locations/{root_loc_id}")
    check("GET /locations/{id} returns location", r2.status_code == 200)

    r2 = get(f"/locations/children/{root_loc_id}")
    check("GET /locations/children/{id} returns children", r2.status_code == 200)

    r2 = put(f"/locations/{root_loc_id}/rename", headers=auth(), json={"name": "Live Root Renamed"})
    check("PUT /locations/{id}/rename renames location", r2.status_code == 200)

# ── Games CRUD ───────────────────────────────────────────────────────────────
section("Games — CRUD")
r = get("/games/")
check("GET /games/ returns list", r.status_code == 200 and isinstance(r.json(), list))

game_payload = {
    "name": "Live Test Game",
    "release_date": 1993,
    "condition": 4,
    "rating": 8,
}
if tag_id:
    game_payload["tag_ids"] = [tag_id]
if coll_id:
    game_payload["collection_id"] = coll_id
if child_loc_id:
    game_payload["location_id"] = child_loc_id
if platforms:
    game_payload["platform_ids"] = [platforms[0]["id"]]
if genres:
    game_payload["genre_ids"] = [genres[0]["id"]]
if modes:
    game_payload["mode_ids"] = [modes[0]["id"]]

r = post("/games/", headers=auth(), json=game_payload)
check("POST /games/ creates game", r.status_code == 200)
game_id = None
if r.status_code == 200:
    game_id = r.json().get("id")

    r2 = get(f"/games/{game_id}")
    check("GET /games/{id} returns game", r2.status_code == 200 and r2.json()["name"] == "Live Test Game")

    r2 = put(f"/games/{game_id}", headers=auth(), json={"condition": 5, "rating": 9})
    check("PUT /games/{id} updates game fields", r2.status_code == 200 and r2.json()["condition"] == 5)

    r2 = get(f"/games/{game_id}/location_path")
    check("GET /games/{id}/location_path returns path", r2.status_code == 200)

check("GET /games/999999 returns 404", get("/games/999999").status_code == 404)
check("PUT /games/999999 returns 404", put("/games/999999", headers=auth(), json={"condition": 1}).status_code == 404)
check("DELETE /games/999999 returns 404", delete("/games/999999", headers=auth()).status_code == 404)

# ── Games — Tags and Platforms via update ────────────────────────────────────
section("Games — Tag & Platform updates via PUT")
if game_id and tag_id:
    # Tags and platforms are managed via PUT /games/{id}, not dedicated sub-routes.
    r = put(f"/games/{game_id}", headers=auth(), json={"tag_ids": [tag_id]})
    check("PUT /games/{id} with tag_ids attaches tags", r.status_code == 200 and any(t["id"] == tag_id for t in r.json().get("tags", [])))

if game_id and platforms:
    r = put(f"/games/{game_id}", headers=auth(), json={"platform_ids": [platforms[0]["id"]]})
    check("PUT /games/{id} with platform_ids attaches platforms", r.status_code == 200 and any(p["id"] == platforms[0]["id"] for p in r.json().get("platforms", [])))

# ── Search ───────────────────────────────────────────────────────────────────
section("Search — Basic")
r = get("/search/basic", params={"name": "Live Test"})
check("GET /search/basic?name= returns results", r.status_code == 200 and "results" in r.json())

r = get("/search/basic", params={"name": "Live Test", "limit": "5"})
check("GET /search/basic respects limit param", r.status_code == 200)

r = get("/search/basic", params={"year": "1993"})
check("GET /search/basic?year= filters by release year", r.status_code == 200)

r = get("/search/basic", params={"year": "notanumber"})
check("GET /search/basic?year=notanumber returns 422", r.status_code == 422)

r = get("/search/basic", params={"limit": "0"})
check("GET /search/basic?limit=0 returns 422", r.status_code == 422)

if platforms:
    r = get("/search/basic", params={"platform_id": platforms[0]["id"]})
    check("GET /search/basic?platform_id= filters by platform", r.status_code == 200)

section("Search — Advanced")
r = get("/search/advanced", params={"name": "Live Test"})
check("GET /search/advanced?name= returns results", r.status_code == 200 and "results" in r.json())

r = get("/search/advanced", params={"year_min": "1990", "year_max": "2000"})
check("GET /search/advanced year range returns results", r.status_code == 200)

r = get("/search/advanced", params={"include_manual": "only"})
check("GET /search/advanced?include_manual=only returns manual games", r.status_code == 200)

r = get("/search/advanced", params={"include_manual": "false"})
check("GET /search/advanced?include_manual=false excludes manual games", r.status_code == 200)

r = get("/search/advanced")
check("GET /search/advanced with no filters returns 400", r.status_code == 400)

r = get("/search/advanced", params={"year": "abc"})
check("GET /search/advanced?year=abc returns 422", r.status_code == 422)

r = get("/search/advanced", params={"include_manual": "invalid"})
check("GET /search/advanced?include_manual=invalid returns 422", r.status_code == 422)

if child_loc_id:
    r = get("/search/advanced", params={"location_id": child_loc_id})
    check("GET /search/advanced?location_id= filters by location", r.status_code == 200)

if root_loc_id:
    r = get("/search/advanced", params={"location_id": root_loc_id, "include_location_descendants": "true"})
    check("GET /search/advanced with descendants finds child games", r.status_code == 200 and len(r.json()["results"]) > 0)

if tag_id and game_id:
    # Re-attach tag for search test
    post(f"/games/{game_id}/tags/{tag_id}", headers=auth())
    r = get("/search/advanced", params={"tag_ids": tag_id, "match_mode": "any"})
    check("GET /search/advanced tag match_mode=any works", r.status_code == 200)
    r = get("/search/advanced", params={"tag_ids": tag_id, "match_mode": "all"})
    check("GET /search/advanced tag match_mode=all works", r.status_code == 200)
    r = get("/search/advanced", params={"tag_ids": tag_id, "match_mode": "exact"})
    check("GET /search/advanced tag match_mode=exact works", r.status_code == 200)

section("Search — Suggestions")
r = get("/search/suggest/names", params={"q": "Li"})
check("GET /search/suggest/names returns suggestions", r.status_code == 200 and "suggestions" in r.json())

r = get("/search/suggest/names", params={"q": "x"})
check("GET /search/suggest/names?q=x returns 400 (too short)", r.status_code == 400)

r = get("/search/suggest/tags", params={"q": "li"})
check("GET /search/suggest/tags returns suggestions", r.status_code == 200)

r = get("/search/suggest/tags", params={"q": "x"})
check("GET /search/suggest/tags?q=x returns 400", r.status_code == 400)

r = get("/search/suggest/igdb_tags", params={"q": "ac"})
check("GET /search/suggest/igdb_tags returns suggestions", r.status_code == 200)

r = get("/search/suggest/modes", params={"q": "si"})
check("GET /search/suggest/modes returns suggestions", r.status_code == 200)

r = get("/search/suggest/collections", params={"q": "li"})
check("GET /search/suggest/collections returns suggestions", r.status_code == 200)

r = get("/search/suggest/companies", params={"q": "ac"})
check("GET /search/suggest/companies returns suggestions", r.status_code == 200)

r = get("/search/suggest/genres", params={"q": "ad"})
check("GET /search/suggest/genres returns suggestions", r.status_code == 200)

r = get("/search/suggest/genres", params={"q": "x"})
check("GET /search/suggest/genres?q=x returns 400", r.status_code == 400)

# ── Files ────────────────────────────────────────────────────────────────────
section("Files")
if game_id:
    r = get(f"/games/{game_id}/files/")
    check("GET /games/{id}/files/ returns file list", r.status_code == 200)

    r = get(f"/games/{game_id}/files/", params={"category": "saves"})
    check("GET /games/{id}/files/?category=saves works", r.status_code == 200)

    upload_resp = post(
        f"/games/{game_id}/files/upload",
        headers=auth(),
        data={"label": "Live test save", "category": "saves"},
        files={"file": ("test.sav", b"live-test-data", "application/octet-stream")},
    )
    check("POST /games/{id}/files/upload uploads file", upload_resp.status_code == 200,
          upload_resp.json().get("detail", "") if upload_resp.status_code != 200 else "")
    file_id = None
    if upload_resp.status_code == 200:
        file_id = upload_resp.json().get("file_id")

        r2 = patch(f"/games/{game_id}/files/{file_id}/label", headers=auth(), json={"label": "Renamed save"})
        check("PATCH /games/{id}/files/{fid}/label renames file", r2.status_code == 200)

        r2 = delete(f"/games/{game_id}/files/{file_id}", headers=auth())
        check("DELETE /games/{id}/files/{fid} removes file", r2.status_code == 204)

r = get("/files/categories")
check("GET /files/categories returns category list", r.status_code == 200)

r = get("/files/sync-all/status", headers=auth())
check("GET /files/sync-all/status returns status", r.status_code == 200)

# ── Stats ────────────────────────────────────────────────────────────────────
section("Stats")
for path in ("/stats/overview", "/stats/health", "/stats/health/cover",
             "/stats/health/release_year", "/stats/health/platform",
             "/stats/health/location", "/stats/health/tag"):
    r = get(path)
    check(f"GET {path} returns 200", r.status_code == 200)

# ── Export ───────────────────────────────────────────────────────────────────
section("Export")
r = get("/export/games/json", headers=auth())
check("GET /export/games/json returns 200", r.status_code == 200)

r = get("/export/games/csv", headers=auth())
check("GET /export/games/csv returns 200", r.status_code == 200)

r = get("/export/games/excel", headers=auth())
check("GET /export/games/excel returns 200", r.status_code == 200)

r = get("/export/games/json")
check("GET /export/games/json without auth returns 401/403", r.status_code in {401, 403})

# ── Backup ───────────────────────────────────────────────────────────────────
section("Backup")
r = get("/backup/list", headers=auth())
check("GET /backup/list returns file list", r.status_code == 200 and isinstance(r.json().get("files"), list))

r = get("/backup/", headers=auth())
check("GET /backup/ streams a pg_dump", r.status_code == 200 and r.content[:5] == b"PGDMP")

r = post("/backup/save", headers=auth())
check("POST /backup/save saves backup", r.status_code == 200 and r.json().get("ok") is True, f"status={r.status_code} body={r.text[:100]}")

r = get("/backup/list")
check("GET /backup/list without auth returns 401/403", r.status_code in {401, 403})

# ── Wishlist ─────────────────────────────────────────────────────────────────
section("Wishlist")
r = get("/wishlist/")
check("GET /wishlist/ returns public active list", r.status_code == 200 and isinstance(r.json(), list))

r = post("/wishlist/", headers=auth(), json={"name": "Live Test Wishlist Game", "release_year": 1994})
check("POST /wishlist/ creates wishlist item", r.status_code == 200)
wl_id = None
if r.status_code == 200:
    wl_id = r.json().get("id")
    r2 = get(f"/wishlist/{wl_id}")
    check("GET /wishlist/{id} returns item (public)", r2.status_code == 200)

    r2 = put(f"/wishlist/{wl_id}", headers=auth(), json={"name": "Updated Wishlist Game", "links": []})
    check("PUT /wishlist/{id} updates wishlist item", r2.status_code == 200 and r2.json()["name"] == "Updated Wishlist Game")

    r2 = get("/wishlist/", params={"status": "active"})
    check("GET /wishlist/?status=active filters correctly", r2.status_code == 200)

    r2 = get("/wishlist/", params={"status": "not-a-status"})
    check("GET /wishlist/?status=invalid returns 422", r2.status_code == 422)

    # Resolve wishlist item with the game we created
    if game_id:
        r2 = post(f"/wishlist/{wl_id}/resolve", headers=auth(), json={"game_id": game_id})
        check("POST /wishlist/{id}/resolve marks item in_library", r2.status_code == 200 and r2.json()["status"] == "in_library")

        r2 = post(f"/wishlist/{wl_id}/resolve", headers=auth(), json={"game_id": game_id})
        check("POST /wishlist/{id}/resolve on already-resolved returns 409", r2.status_code == 409)

r = post("/wishlist/", json={"name": "Unauth wishlist"})
check("POST /wishlist/ without auth returns 401/403", r.status_code in {401, 403})

# Wishlist item for purchase test
r = post("/wishlist/", headers=auth(), json={"name": "Purchase Test Game"})
if r.status_code == 200:
    purchase_wl_id = r.json()["id"]
    r2 = post(f"/wishlist/{purchase_wl_id}/purchase", headers=auth(), json={"condition": 3})
    check("POST /wishlist/{id}/purchase creates game from wishlist", r2.status_code == 200 and r2.json().get("igdb_id") == 0)
    created_game_id = r2.json().get("id")

    r2 = post(f"/wishlist/{purchase_wl_id}/purchase", headers=auth(), json={})
    check("POST /wishlist/{id}/purchase on already-purchased returns 409", r2.status_code == 409)

    # Cleanup
    if created_game_id:
        delete(f"/games/{created_game_id}", headers=auth())

# ── Purchase Link Shortcuts ───────────────────────────────────────────────────
section("Purchase Link Shortcuts")
base_pls = "/purchase-link-shortcuts/"
r = get(base_pls, headers=auth())
check("GET /purchase-link-shortcuts/ returns list (admin)", r.status_code == 200)

r = get(base_pls)
check("GET /purchase-link-shortcuts/ without auth returns 401/403", r.status_code in {401, 403})

r = post(base_pls, headers=auth(), json={"label": "Live Test Shop", "sort_order": 99})
check("POST /purchase-link-shortcuts/ creates shortcut", r.status_code == 201)
pls_id = None
if r.status_code == 201:
    pls_id = r.json().get("id")

    r2 = post(base_pls, headers=auth(), json={"label": "Live Test Shop"})
    check("POST /purchase-link-shortcuts/ duplicate label returns 409", r2.status_code == 409)

    r2 = put(f"{base_pls}{pls_id}", headers=auth(), json={"label": "Live Test Shop Renamed", "sort_order": 99})
    check("PUT /purchase-link-shortcuts/{id} updates shortcut", r2.status_code == 200)

    r2 = put(f"{base_pls}reorder", headers=auth(), json={"items": [{"id": pls_id, "sort_order": 1}]})
    check("PUT /purchase-link-shortcuts/reorder reorders shortcuts", r2.status_code == 200)

    r2 = delete(f"{base_pls}{pls_id}", headers=auth())
    check("DELETE /purchase-link-shortcuts/{id} removes shortcut", r2.status_code == 204)

r = post(base_pls, headers=auth(), json={"label": "   "})
check("POST /purchase-link-shortcuts/ with blank label returns 422", r.status_code == 422)

# ── Cover Images ─────────────────────────────────────────────────────────────
section("Cover Images")

# igdb_id is not in GamePreview; use cover_url presence as proxy for IGDB-backed
_all_games = get("/games/").json() if get("/games/").status_code == 200 else []
_igdb_game = next((g for g in _all_games if g.get("cover_url")), None)
_custom_game = next((g for g in _all_games if not g.get("cover_url")), None)

# cover_cached field is present in game list and detail responses
check(
    "GET /games/ response includes cover_cached field",
    _all_games and "cover_cached" in _all_games[0],
)
if _igdb_game:
    r = get(f"/games/{_igdb_game['id']}")
    check(
        "GET /games/{id} response includes cover_cached field",
        r.status_code == 200 and "cover_cached" in r.json(),
    )

# cover/status — public, no auth required
if _igdb_game:
    r = get(f"/games/{_igdb_game['id']}/cover/status")
    check("GET /games/{id}/cover/status returns 200 (no auth)", r.status_code == 200)
    d = r.json()
    check(
        "cover/status has cover_cached and igdb_cover_url fields",
        "cover_cached" in d and "igdb_cover_url" in d,
    )

# cover/status 404 for unknown game
r = get("/games/999999/cover/status")
check("GET /games/999999/cover/status returns 404", r.status_code == 404)

# GET /cover — public; falls back to IGDB redirect when not cached
if _igdb_game:
    r = get(f"/games/{_igdb_game['id']}/cover", allow_redirects=False)
    check(
        "GET /games/{id}/cover redirects when not cached (uncached game)",
        r.status_code == 307 and r.headers.get("location", "").startswith("https://"),
    )

# auth guards on admin endpoints
if _igdb_game:
    r = post(f"/games/{_igdb_game['id']}/cover/cache")
    check("POST /games/{id}/cover/cache without auth returns 401/403", r.status_code in {401, 403})
    r = delete(f"/games/{_igdb_game['id']}/cover")
    check("DELETE /games/{id}/cover without auth returns 401/403", r.status_code in {401, 403})

r = post("/games/sync-cover-images")
check("POST /games/sync-cover-images without auth returns 401/403", r.status_code in {401, 403})
r = get("/games/sync-cover-images/status")
check("GET /games/sync-cover-images/status without auth returns 401/403", r.status_code in {401, 403})

# cache IGDB cover for a specific game
_cover_test_id = None
if _igdb_game:
    _cover_test_id = _igdb_game["id"]
    r = post(f"/games/{_cover_test_id}/cover/cache", headers=auth())
    check("POST /games/{id}/cover/cache succeeds (admin)", r.status_code == 200 and r.json().get("cached") is True)

    # now the cover should be served directly (200, image/jpeg)
    r = get(f"/games/{_cover_test_id}/cover", allow_redirects=True)
    check(
        "GET /games/{id}/cover serves image after caching",
        r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"),
    )

    # status reflects cached=True
    r = get(f"/games/{_cover_test_id}/cover/status")
    check(
        "cover/status shows cover_cached=True after caching",
        r.status_code == 200 and r.json().get("cover_cached") is True,
    )

    # caching again returns already-cached message (idempotent)
    r = post(f"/games/{_cover_test_id}/cover/cache", headers=auth())
    check(
        "POST /games/{id}/cover/cache is idempotent (already cached)",
        r.status_code == 200 and r.json().get("cached") is True,
    )

    # delete the cached cover
    r = delete(f"/games/{_cover_test_id}/cover", headers=auth())
    check("DELETE /games/{id}/cover removes cached cover", r.status_code == 200)

    # status reflects cached=False again
    r = get(f"/games/{_cover_test_id}/cover/status")
    check(
        "cover/status shows cover_cached=False after deletion",
        r.status_code == 200 and r.json().get("cover_cached") is False,
    )

# custom cover upload for any game
if _custom_game or _igdb_game:
    _upload_target = (_custom_game or _igdb_game)["id"]
    import io
    # minimal valid 1×1 PNG
    _png = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00'
        b'\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    r = post(
        f"/games/{_upload_target}/cover",
        headers=auth(),
        files={"file": ("cover.png", io.BytesIO(_png), "image/png")},
    )
    check("POST /games/{id}/cover uploads custom cover", r.status_code == 200)

    r = get(f"/games/{_upload_target}/cover", allow_redirects=True)
    check(
        "GET /games/{id}/cover serves uploaded custom cover",
        r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"),
    )

    # clean up uploaded cover
    delete(f"/games/{_upload_target}/cover", headers=auth())

# sync-cover-images/status is accessible to admin
r = get("/games/sync-cover-images/status", headers=auth())
check("GET /games/sync-cover-images/status returns status (admin)", r.status_code == 200 and "status" in r.json())

# ── Maintenance ───────────────────────────────────────────────────────────────
section("Maintenance")
r = get("/admin/maintenance/status")
check("GET /admin/maintenance/status returns status", r.status_code == 200)

r = post("/admin/maintenance/enter")
check("POST /admin/maintenance/enter enables maintenance (no auth required)", r.status_code == 200)

r = get("/health")
check("GET /health works during maintenance", r.status_code == 200)

r = get("/games/")
check("GET /games/ returns 503 during maintenance", r.status_code == 503)

r = post("/admin/maintenance/exit")
check("POST /admin/maintenance/exit disables maintenance", r.status_code == 200)

r = get("/games/")
check("GET /games/ returns 200 after maintenance exit", r.status_code == 200)

# ── Cleanup ───────────────────────────────────────────────────────────────────
section("Cleanup")
if game_id:
    r = delete(f"/games/{game_id}", headers=auth())
    check("DELETE /games/{id} removes test game", r.status_code == 200)
    r2 = get(f"/games/{game_id}")
    check("GET /games/{id} returns 404 after delete", r2.status_code == 404)

if tag_id:
    r = delete(f"/tags/{tag_id}", headers=auth())
    check("DELETE /tags/{id} removes test tag", r.status_code == 200)

if child_loc_id:
    delete(f"/locations/{child_loc_id}", headers=auth())
if root_loc_id:
    r = delete(f"/locations/{root_loc_id}", headers=auth())
    check("DELETE /locations/{id} removes test location", r.status_code == 204)

# Collections have no DELETE endpoint — they are created via IGDB lookup only.

# ── Summary ───────────────────────────────────────────────────────────────────
total = len(passes) + len(failures)
print(f"\n{'═' * 64}")
print(f"  {len(passes)}/{total} passed", end="")
if failures:
    print(f"   ({len(failures)} failed)")
    print("\nFailed:")
    for f in failures:
        print(f"  ✗ {f}")
else:
    print("  — all good!")
print(f"{'═' * 64}")

sys.exit(0 if not failures else 1)
