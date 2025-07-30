import os
import sys
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import get_authenticated_client

BASE = "http://localhost:8000"
IGDB_IDS = [262186, 666, 1273]

client = get_authenticated_client()

for igdb_id in IGDB_IDS:
    print(f"Searching IGDB game {igdb_id}...")
    resp = client.get(f"/igdb/game/{igdb_id}")
    assert resp.status_code == 200
    meta = resp.json()
    print("Fetched:", meta["name"])
    platforms = meta["platforms"]
    platform_ids = [platforms[0]["id"]] if platforms else []

    print(f"Creating local game for IGDB {igdb_id} with platforms {platform_ids}...")
    resp = client.post(f"/games/from_igdb", json={
        "igdb_id": igdb_id,
        "platform_ids": platform_ids,
        "location_id": None,
        "tag_ids": [],
        "condition": 1,
        "order": 0
    })
    print("Status:", resp.status_code, resp.text)
