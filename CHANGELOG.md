# Changelog

## Unreleased

### Upgrade notes
- **Everyone logs in once more.** Login tokens are now bound to the password they were issued for; tokens from
  earlier releases are refused.
- **Changing your password now signs you out everywhere** (including the browser you changed it in), so it can
  also be used to cut off any session you don't trust. It also makes a leaked `SECRET_KEY` useless once the
  password has changed.
- **Behind a reverse proxy?** Set `PROXY=true` (it already controls secure cookies): the login rate limit then
  counts failed logins per visitor, using `X-Forwarded-For`. `TRUSTED_PROXY_HOPS` (default `1`) says how many
  proxies append to that header. Without `PROXY=true` the limit stays shared by everyone, as before.

### New
- **Fill order gaps** (Admin → Location Manager). Select a location and renumber its games so they count
  1, 2, 3… left to right with no gaps or duplicates, for example after games were taken off the shelf. Optionally
  include all sub-locations; each one is numbered on its own. Manual only, with a preview first (including a
  CSV of every old → new number); applying writes exactly what was previewed, all-or-nothing, and is refused if
  the games changed in between. Games that share a number are split in the order they were added and listed so
  you can check them on the shelf; games without an order are left alone. A dual jewel case counts as one game.

### Changes
- **Login rate limit per visitor.** The API only ever saw the web server's address, so three bad guesses from
  anyone (a scanner, an attacker) locked the real admin out for a minute, repeatably.
- **Stale admin sessions send you to the login page** instead of leaving a logged-in-looking page where every
  action fails with "Invalid token" (after a password change, a `SECRET_KEY` rotation, or token expiry).
- **Logging out from another website is ignored** (it was a plain GET that any site could trigger).
- **A job killed by an API restart no longer shows as "running" forever;** it is marked "interrupted" at startup.
- **IGDB client:** honours `Retry-After` when rate-limited (capped at 10 s) and replaces a revoked or expired
  token once instead of failing until it expires on its own.
- The API route-inventory test now lists the cover, cover-sync, genre-suggestion, update-status and
  delete-impact routes, so the test suite is green.

- **Force-refreshing metadata** no longer zeroes every game's timestamp before contacting IGDB: a failed
  run (IGDB down, rate-limited, bad key) used to flag the whole library as "update available" and lose the
  stored timestamps. It now changes nothing on failure; one game's database error no longer fails the games
  after it, and the job no longer holds a database connection idle for its whole run.
- **`scripts/build-release.sh`** (API and Web repositories): builds a release image from a clean `git archive`
  export of a commit, then verifies the final filesystem **and every layer** for `.env`, `storage/`, `.git`,
  database dumps and session keys before anything can be pushed. `--check-image IMAGE` checks an image that
  already exists, for example one pulled from Docker Hub.

## 3.4.x — API 3.4.2 / Web 3.4.2 (October 2026)

A security, reliability and performance release. **API and Web must be updated together.**
There is **no database migration**, and `update.sh` now takes a database backup before it changes anything.

### Upgrade notes — please read

- **Everyone has to log in again once.** Admin sessions now carry a server-side proof cookie.
- **The containers no longer run as root.** On first start they `chown` the contents of `./storage` to
  uid:gid `1000:1000` (override with `APP_UID` / `APP_GID`), then drop privileges. If you set an explicit
  `user:` in compose, make sure `./storage` is writable by it. A volume that refuses `chown` (some NFS setups)
  logs a warning.
- **`GET /igdb/search` now requires an admin login.** Anything that called it anonymously gets a 401.
- **Browser security headers were added** (Content-Security-Policy with per-request nonces, COOP, CORP,
  Permissions-Policy) and **state-changing requests are checked against the site's `Origin`**.
  If you run behind a reverse proxy that rewrites the `Host` header without sending `X-Forwarded-Host`,
  logins can be refused with a 403: set `ALLOWED_ORIGINS=https://your.host`, or `CSRF_ORIGIN_CHECK=off`.
  Emergency switch for the CSP: `CSP_MODE=report-only` (or `off`).
- **Pinned versions.** The web image moved from Node 25 (not an LTS line) to Node 24 LTS; the API image is
  `python:3.14-slim-trixie`; `pandas`, `numpy`, `pydantic` and `starlette` are pinned.
- **Published images no longer contain `.env`, `storage/` or `.git`.** Images before this release could.
  If you ever ran an older `rootifera/gamecubby-api` image, treat the credentials and database dumps that were
  inside it as exposed and rotate them (S3 keys, IGDB/Twitch secret, admin password, `SECRET_KEY`).
- **New optional settings** (all have defaults, see `.env.default`): `BACKUP_MIN_KEEP`, `DB_POOL_SIZE`,
  `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_STATEMENT_TIMEOUT_MS`, `THREADPOOL_SIZE`, `CSP_MODE`,
  `CSRF_ORIGIN_CHECK`, `ALLOWED_ORIGINS`.

### Security
- Restore, backup, bootstrap and maintenance routes verify the admin session properly; before, a hand-made
  cookie was accepted.
- Fixed a reflected XSS and an open redirect on the login flow.
- State-changing requests from another site are rejected; security headers added (see above).
- The Twitch/IGDB client secret is no longer sent in URL query strings, which put it in error messages and logs.
- Images are built with a `.dockerignore`, so local files such as `.env` and `storage/` can no longer be copied in.

### Reliability
- **A flood of requests can no longer freeze the API.** Public endpoints no longer run blocking database calls
  on the event loop, the request thread pool is kept below the connection pool, pool waits time out in 10 s
  and answer `503` + `Retry-After`, and any single SQL statement is limited to 30 s.
- **Backups:** every backup gets a SHA-256 checksum and is written atomically; restore verifies the checksum
  and the dump before touching the database, takes a pre-restore snapshot by default and **rolls back
  automatically** if the restore fails; pruning always keeps the newest `BACKUP_MIN_KEEP` backups; the Backups
  page shows when the last backup failed or the S3 listing is broken; restore logs now live on the persistent
  volume. Only one backup/restore job can run at a time.
- **Files stay consistent with the database:** renaming a custom game, converting an IGDB game to custom, and
  deleting or uploading a file no longer leave files and database disagreeing after a failure. Games that
  share files (same IGDB id) never lose them because a copy changed.
- **Cover sync checks storage** instead of trusting a flag, so covers deleted from S3 or disk are noticed
  and restored.
- The maintenance flag is read from its file directly (no 12-hour cookie that could outlive maintenance).
- Containers have health checks, and the web container waits for the API to be healthy.
- Downloads support `Range` requests (resume/seek); proxy routes have timeouts and stop when the client leaves.

### Performance
- Search and export no longer run a query per game: a search of 100 games went from 1,371 database queries
  to 9, a full export from 5,423 to 15 (JSON export: 10.9 s → 0.3 s).
- Cover requests dropped from about 11 database queries to about 1 (settings are cached briefly); S3 clients are reused.
- Large S3 uploads and the nightly backup no longer block other requests.

### Features
- **Deleting a game has an "Also delete all files" option** (off by default). By default a game's files are
  always kept, because copies of the same game share them; the option shows how many files and which other
  copies would lose them before you confirm.
