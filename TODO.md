# Security & Hardening TODO

Items identified during a security review of this repository.

## High Priority

- [x] **Stop serving recordings via public `/local/` URLs**
  - Recordings are stored under `www/reolink_recordings` and exposed as `/local/reolink_recordings/recordings/...` in `sensor.py`.
  - Home Assistant serves `/local/` without authentication — anyone who can reach the instance may access surveillance footage.
  - **Fix:** Move storage outside `www/` (e.g. under the HA config directory), update default `storage_path`, and serve media through the authenticated media source (`/media-source/reolink_recordings/...`) instead of `/local/`.

## Medium Priority

- [x] **Redact tokens from debug logs** (`coordinator.py`)
  - WebSocket auth requests log the full `access_token` at debug level (line ~866).
  - Download requests log `Authorization` headers at debug level (line ~940).
  - **Fix:** Redact or omit sensitive fields before logging.

- [x] **Validate credentials during config flow** (`config_flow.py`)
  - Setup accepts any host/username/password without verifying the long-lived access token works.
  - **Fix:** Test the token against HA's WebSocket or REST API during `async_step_user` before creating the config entry.

- [ ] **Fix XSS risk in custom Lovelace cards**
  - `frontend/reolink-recording-card.js` and `frontend/reolink-summary-card.js` inject entity data (camera names, event types, timestamps) into `innerHTML` without escaping.
  - **Fix:** Use `textContent`, DOM APIs, or an HTML-escape helper for all dynamic values.

- [ ] **Remove filesystem path from public entity attributes** (`sensor.py`)
  - `file_path` exposes the full local path in `extra_state_attributes`.
  - **Fix:** Remove `file_path` from attributes or expose only the filename / media-source identifier.

- [x] **Fix `ssl=None` on WebSocket connections** (`coordinator.py`, line ~808)
  - `websockets.connect(websocket_url, ssl=None)` may disable or bypass proper TLS verification for `wss://` connections.
  - **Fix:** Use the default SSL context for `wss://` (or an explicit verified context); only omit SSL for plain `ws://` localhost connections if needed.

## Low Priority

- [x] **Improve token storage pattern**
  - Long-lived access token is stored in `CONF_PASSWORD`; `CONF_USERNAME` is unused.
  - **Fix:** Consider a dedicated config key (e.g. `access_token`) with a config entry migration for existing installs.

- [x] **Restrict the refresh service to admin users** (`__init__.py`)
  - `reolink_recordings.refresh` triggers full re-downloads using the stored token with no explicit permission check.
  - **Fix:** Register as an admin-only service or verify caller permissions in the handler.

- [x] **Validate `storage_path` option** (`config_flow.py`, `__init__.py`)
  - Admins can set `storage_path` to any path under the HA config tree with no validation.
  - **Fix:** Allow absolute paths; keep relative paths under config (reject `..`); warn if under `www/`.

- [x] **Use unique temp files for ffmpeg GIF generation** (`coordinator.py`)
  - GIF generation writes to a shared `/tmp/palette.png`, which can collide when multiple instances run concurrently.
  - **Fix:** Use `tempfile` or a UUID-based temp path per invocation.

## Documentation & API Consistency

- [x] **Reconcile manual refresh / redownload services**
  - Chose Option B: only `reolink_recordings.refresh` is registered and documented.
  - Removed unused `SERVICE_FETCH_LATEST` / `SERVICE_DOWNLOAD_RECORDING` constants.
  - `services.yaml`, translations, and README all document `refresh` (optional `entry_id`, admin-only).

- [x] **Document device triggers and redownload automations** (`README.md`)
  - Documented `recording_updated`, `vehicle_detected`, `person_detected`, `motion_detected`.
  - Documented `reolink_recordings_updated` event data and example automations (notify + scheduled refresh).

- [x] **Document event-driven discovery options** (`README.md`)
  - Documented `enable_event_driven`, `upload_delay`, motion-sensor mapping, and how they relate to scan interval and manual refresh.

- [x] **Keep CI/service docs in sync after service reconciliation**
  - README services section, `services.yaml`, and automation examples match the registered `refresh` handler.

## CI

`.github/workflows/validate.yml` runs on pull requests with hassfest, Ruff, and ESLint. README documents how to run the same checks locally.

### Essential

- [x] **Add hassfest validation**
  - Uses `home-assistant/actions/hassfest@master` in `.github/workflows/validate.yml`.

- [ ] **Add HACS validation**
  - Required before HACS default-store submission (README notes HACS is not yet available).
  - Use `hacs/action@main` with `category: integration`.

### Recommended

- [x] **Add Ruff for Python linting**
  - Runs via `astral-sh/ruff-action@v3` in CI; `ruff check .` locally.

- [ ] **Add Bandit (or similar) for security static analysis**
  - Complements the security items above (subprocess usage, logging patterns, etc.).
  - Does not replace manual review.

### Later

- [ ] **Add pytest with Home Assistant test helpers**
  - No tests exist yet; meaningful coverage would need HA's test harness.
  - Good targets: coordinator merge/slug logic, path handling, config validation.

- [x] **Add ESLint for Lovelace cards**
  - Lints `custom_components/reolink_recordings/frontend/` in CI (`npm run lint`).

### Suggested workflow layout

Consider extending `validate.yml` with HACS validation and optional Bandit, and adding `push` / scheduled triggers if you want coverage beyond pull requests.

### What CI will not catch

These require code changes from the security section above, not automation alone:

- XSS in custom cards (ESLint helps only with rules that catch unsafe `innerHTML` usage)
- Removing `file_path` from public entity attributes
