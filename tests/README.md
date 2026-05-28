# Tests

The previous test suite was removed because it no longer represented the
current API behavior reliably.

New tests should be added deliberately as endpoints and internals are cleaned
up. Prefer characterization tests that document the behavior we want to keep,
especially for bootstrap, maintenance, authentication, storage, and IGDB flows.
