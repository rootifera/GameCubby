# Wishlist-to-library reconciliation

Wishlist entries remain as an audit trail after their games are added to the library.

## Migration

Run Alembic through revision `c6e4b1a9d720` (`add wishlist reconciliation`). It adds these columns to `wishlist_items`:

- `status`: non-null string, defaulting to `active`; valid application values are `active` and `in_library`.
- `library_game_id`: nullable foreign key to `games.id`.

## Wishlist reads

`GET /wishlist/` preserves its previous behavior and returns only active entries.

Optional filters:

- `GET /wishlist/?status=active`
- `GET /wishlist/?status=in_library`
- `GET /wishlist/?include_resolved=true`

Each Wishlist entry now contains `status` and `library_game_id` in addition to its existing fields.

```json
{
  "id": 55,
  "igdb_id": 7346,
  "name": "Example Game",
  "release_year": 1998,
  "status": "in_library",
  "library_game_id": 123,
  "platforms": [],
  "links": []
}
```

## Explicit resolution

`POST /wishlist/{wishlist_id}/resolve` requires admin authentication.

```json
{ "game_id": 123 }
```

The operation locks the active Wishlist row, verifies the target library game exists, then atomically sets `status` to `in_library` and `library_game_id` to the game ID. It returns the updated Wishlist entry.

- `404`: Wishlist item does not exist.
- `409`: Wishlist item was already resolved.
- `422`: target game does not exist or the request ID is invalid.

## Integrated game creation

Both authenticated game creation endpoints accept optional `wishlist_id`:

- `POST /games/`
- `POST /games/from_igdb`

When provided, the backend creates the normal library game and resolves the active Wishlist entry in a single transaction. A failure in either operation rolls back both changes.

For example:

```json
{
  "igdb_id": 7346,
  "platform_ids": [48],
  "location_id": 12,
  "wishlist_id": 55
}
```

The normal game response remains unchanged apart from its optional `matching_wishlist_ids` array. For regular IGDB creation without `wishlist_id`, it contains exact-ID matches for active Wishlist entries only. It is advisory: the backend never resolves or deletes entries based on a name match.

```json
{
  "id": 123,
  "igdb_id": 7346,
  "name": "Example Game",
  "matching_wishlist_ids": [55, 68]
}
```

Manual game creation always returns an empty `matching_wishlist_ids` array unless a future advisory matcher is introduced.

## Legacy purchase endpoint

`POST /wishlist/{wishlist_id}/purchase` remains available for existing callers. Internally it uses the same transactional game-creation and reconciliation services. It now marks the Wishlist entry `in_library` rather than deleting it.
