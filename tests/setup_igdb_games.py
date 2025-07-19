import requests

BASE = "http://localhost:8000"
IGDB_IDS = [262186, 666, 1273]

for igdb_id in IGDB_IDS:
    print(f"Searching IGDB game {igdb_id}...")
    meta = requests.get(f"{BASE}/igdb/game/{igdb_id}").json()
    print("Fetched:", meta["name"])
    platforms = meta["platforms"]
    platform_ids = [platforms[0]["id"]] if platforms else []
    print(f"Creating local game for IGDB {igdb_id} with platforms {platform_ids}...")
    resp = requests.post(f"{BASE}/games/from_igdb", json={
        "igdb_id": igdb_id,
        "platform_ids": platform_ids,
        "location_id": None,
        "tag_ids": [],
        "condition": 1,
        "order": 0
    })
    print("Status:", resp.status_code, resp.text)
