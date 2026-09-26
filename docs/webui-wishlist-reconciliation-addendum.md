# WebUI Wishlist Reconciliation Addendum

Backend update: Wishlist reconciliation is now implemented.

Wishlist entries are retained after purchase and now include:

- `status`: `"active"` or `"in_library"`
- `library_game_id`: the normal library game ID once resolved

`GET /wishlist/` returns active entries by default. Use:

- `GET /wishlist/?status=in_library` for resolved entries
- `GET /wishlist/?include_resolved=true` for all entries

Do not use `POST /wishlist/{id}/purchase` for new UI work. Keep using the existing Add Game form and normal creation endpoints:

- `POST /games/`
- `POST /games/from_igdb`

When the user starts from a Wishlist item, include its ID as `wishlist_id` in the existing add-game request. The backend atomically creates the normal game and marks the Wishlist entry as `in_library`; it does not delete the Wishlist record.

```json
{
  "igdb_id": 7346,
  "platform_ids": [48],
  "location_id": 12,
  "condition": 4,
  "tag_ids": [1, 7],
  "wishlist_id": 55
}
```

For an explicit follow-up action, the backend also provides:

`POST /wishlist/{wishlist_id}/resolve`

```json
{ "game_id": 123 }
```

This requires admin authentication and returns the updated Wishlist item. It returns `409` if already resolved.

Regular IGDB game creation without `wishlist_id` now includes:

```json
{
  "matching_wishlist_ids": [55, 68]
}
```

These are exact active IGDB-ID matches only. Do not auto-resolve based on a matching game name. The UI may offer an explicit action to resolve one of these entries.
