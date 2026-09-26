# GameCubby WebUI Wishlist Implementation Prompt

```text
Add a complete Wishlist feature to GameCubby-Web. The backend is already implemented and available through the existing API integration.

Match the existing GameCubby visual language, routing, authentication, API proxy patterns, loading states, error handling, and admin-only mutation behavior. Inspect the existing Games pages and IGDB add-game flow before implementing.

Build a Wishlist section accessible from the main navigation.

Requirements

1. Wishlist list page
- Add a `/wishlist` page.
- Fetch `GET /wishlist/`.
- Show each item’s cover image where available, name, release year, selected platform(s), and purchase links.
- Each purchase link should render using its saved label, for example “eBay”, “CeX”, or “Local shop”, and open externally in a new tab safely.
- Include controls to add, edit, delete, and mark an item as Purchased.
- Public users may browse; editing actions must follow the app’s existing admin authentication behavior.

2. Add wishlist item
- Provide an “Add to Wishlist” flow similar to the existing “Add Game from IGDB” flow.
- Reuse the existing IGDB search endpoint: `GET /igdb/search?q=...`.
- After a user selects an IGDB result, allow platform selection and optional labelled purchase links.
- Save the selected item through:

  `POST /wishlist/from_igdb`

  Request body:
  ```json
  {
    "igdb_id": 7346,
    "platform_ids": [48],
    "links": [
      {
        "label": "eBay",
        "url": "https://www.ebay.co.uk/..."
      }
    ]
  }
  ```

- If no platform IDs are sent, the backend saves all platforms returned by IGDB. The UI should normally encourage the user to choose the platform(s) they actually want.
- Also provide a manual-entry option using `POST /wishlist/`.

  Request body:
  ```json
  {
    "name": "Example Game",
    "release_year": 1998,
    "cover_url": "https://example.com/cover.jpg",
    "platform_ids": [6],
    "links": [
      {
        "label": "eBay",
        "url": "https://www.ebay.co.uk/..."
      }
    ]
  }
  ```

- Fetch `GET /platforms/` for manual-entry platform selection.

3. Edit wishlist item
- Add an edit view or modal.
- Fetch an individual item with `GET /wishlist/{wishlist_id}` when needed.
- Save edits through `PUT /wishlist/{wishlist_id}`.
- The update payload may include `name`, `release_year`, `cover_url`, `platform_ids`, and `links`.
- When `platform_ids` or `links` are included, they replace the previous values. Preserve values that the user does not change.
- Support adding, changing, and removing any number of purchase links.

4. Delete
- Delete through `DELETE /wishlist/{wishlist_id}`.
- Use the project’s established confirmation pattern before deletion.
- Refresh or optimistically update the list after success.

5. Purchased flow
- Each item needs a clear `Purchased` button.
- Use the existing Add Game form and normal `POST /games/` or `POST /games/from_igdb` flow. Do not create a second game-creation workflow.
- Pass the active Wishlist ID as `wishlist_id` with the usual location, condition, order, and optional personal tags.
- The backend creates the normal game and atomically marks the Wishlist item `in_library`. It does not delete the Wishlist record.
- On success, redirect to the new game detail page and refresh the Wishlist list; its default view returns active entries only.

Backend response shape

```json
{
  "id": 1,
  "igdb_id": 7346,
  "name": "Example Game",
  "release_year": 2024,
  "cover_url": "https://...",
  "platforms": [
    { "id": 48, "name": "PlayStation 4", "slug": "ps4" }
  ],
  "links": [
    {
      "id": 1,
      "label": "eBay",
      "url": "https://www.ebay.co.uk/..."
    }
  ]
}
```

All POST, PUT, DELETE, `/from_igdb`, and `/purchase` requests require the existing admin bearer token. GET list/detail endpoints are public.

Do not change existing game-library behavior or API contracts. Add appropriate TypeScript types, API/proxy routes if the app uses them, and tests consistent with the existing WebUI project.
```
