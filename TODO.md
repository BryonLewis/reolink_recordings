# Security & Hardening TODO

Items identified during a security review of this repository.

## High Priority

- [ ] **Stop serving recordings via public `/local/` URLs**
  - Recordings are stored under `www/reolink_recordings` and exposed as `/local/reolink_recordings/recordings/...` in `sensor.py`.
  - Home Assistant serves `/local/` without authentication — anyone who can reach the instance may access surveillance footage.
  - **Fix:** Move storage outside `www/` (e.g. under the HA config directory), update default `storage_path`, and serve media through the authenticated media source (`/media-source/reolink_recordings/...`) instead of `/local/`.

## Medium Priority

- [ ] **Redact tokens from debug logs** (`coordinator.py`)
  - WebSocket auth requests log the full `access_token` at debug level (line ~866).
  - Download requests log `Authorization` headers at debug level (line ~940).
  - **Fix:** Redact or omit sensitive fields before logging.

- [ ] **Validate credentials during config flow** (`config_flow.py`)
  - Setup accepts any host/username/password without verifying the long-lived access token works.
  - **Fix:** Test the token against HA's WebSocket or REST API during `async_step_user` before creating the config entry.

- [ ] **Fix XSS risk in custom Lovelace cards**
  - `frontend/reolink-recording-card.js` and `frontend/reolink-summary-card.js` inject entity data (camera names, event types, timestamps) into `innerHTML` without escaping.
  - **Fix:** Use `textContent`, DOM APIs, or an HTML-escape helper for all dynamic values.

- [ ] **Remove filesystem path from public entity attributes** (`sensor.py`)
  - `file_path` exposes the full local path in `extra_state_attributes`.
  - **Fix:** Remove `file_path` from attributes or expose only the filename / media-source identifier.

- [ ] **Fix `ssl=None` on WebSocket connections** (`coordinator.py`, line ~808)
  - `websockets.connect(websocket_url, ssl=None)` may disable or bypass proper TLS verification for `wss://` connections.
  - **Fix:** Use the default SSL context for `wss://` (or an explicit verified context); only omit SSL for plain `ws://` localhost connections if needed.

## Low Priority

- [ ] **Improve token storage pattern**
  - Long-lived access token is stored in `CONF_PASSWORD`; `CONF_USERNAME` is unused.
  - **Fix:** Consider a dedicated config key (e.g. `access_token`) with a config entry migration for existing installs.

- [ ] **Restrict the refresh service to admin users** (`__init__.py`)
  - `reolink_recordings.refresh` triggers full re-downloads using the stored token with no explicit permission check.
  - **Fix:** Register as an admin-only service or verify caller permissions in the handler.

- [ ] **Validate `storage_path` option** (`config_flow.py`, `__init__.py`)
  - Admins can set `storage_path` to any path under the HA config tree with no validation.
  - **Fix:** Constrain paths to an expected directory (e.g. under config root, reject `www/` for recordings).

- [ ] **Use unique temp files for ffmpeg GIF generation** (`coordinator.py`)
  - GIF generation writes to a shared `/tmp/palette.png`, which can collide when multiple instances run concurrently.
  - **Fix:** Use `tempfile` or a UUID-based temp path per invocation.

## Documentation & API Consistency

Services, triggers, and README are out of sync with the code.

- [ ] **Reconcile manual refresh / redownload services**
  - **Implemented:** `reolink_recordings.refresh` in `__init__.py` (optional `entry_id`), calls `coordinator.async_refresh()`.
  - **Documented in README:** `reolink_recordings.fetch_latest_recordings` and `reolink_recordings.download_recording` — neither is registered in code.
  - **Declared in `services.yaml`:** `fetch_latest_recordings` and `download_recording` — also not registered.
  - **Constants in `const.py`:** `SERVICE_FETCH_LATEST` and `SERVICE_DOWNLOAD_RECORDING` — unused.
  - **Fix:** Pick one approach and align everything:
    - Option A: Implement the documented services (`fetch_latest_recordings` → full refresh; `download_recording` → single-camera download via existing `_discover_and_download_camera`), and keep or alias `refresh`.
    - Option B: Remove the unused constants and update `services.yaml` + README to document only `reolink_recordings.refresh`.

- [ ] **Document device triggers and redownload automations** (`README.md`)
  - `device_trigger.py` exposes per-camera triggers: `recording_updated`, `vehicle_detected`, `person_detected`, `motion_detected` (translations in `translations/en.json`).
  - README mentions using sensor attributes in automations but does not document device triggers or example automations for reacting to new recordings / triggering a redownload.
  - **Fix:** Add a section covering available device triggers, the `reolink_recordings_updated` event, and example automation YAML (e.g. call the refresh service when a recording updates).

- [ ] **Document event-driven discovery options** (`README.md`)
  - Config flow supports `enable_event_driven`, `upload_delay`, and motion-sensor-to-camera mapping (`config_flow.py`, `coordinator.py`).
  - README configuration options omit these entirely.
  - **Fix:** Document how motion-sensor-triggered discovery works and how it relates to periodic scan interval and manual refresh.

- [ ] **Keep CI/service docs in sync after service reconciliation**
  - Once services are aligned, update `services.yaml`, README, and any automation examples together so hassfest and user docs match registered handlers.

## CI

No CI is configured today (no `.github/workflows`, tests, or lint config). Recommended additions, in priority order:

### Essential

- [ ] **Add hassfest validation**
  - Validates `manifest.json`, translations, config flow, and `services.yaml` against Home Assistant core requirements.
  - Use `home-assistant/actions/hassfest@master` in a GitHub Actions workflow.
  - May already flag mismatches: see **Documentation & API Consistency** — `services.yaml` and README do not match the registered `refresh` service.

- [ ] **Add HACS validation**
  - Required before HACS default-store submission (README notes HACS is not yet available).
  - Use `hacs/action@main` with `category: integration`.

### Recommended

- [ ] **Add Ruff for Python linting**
  - Low-effort static analysis across `coordinator.py`, `config_flow.py`, `sensor.py`, etc.
  - No test suite required.

- [ ] **Add Bandit (or similar) for security static analysis**
  - Complements the security items above (subprocess usage, logging patterns, etc.).
  - Does not replace manual review.

### Later

- [ ] **Add pytest with Home Assistant test helpers**
  - No tests exist yet; meaningful coverage would need HA's test harness.
  - Good targets: coordinator merge/slug logic, path handling, config validation.

- [ ] **Add ESLint for Lovelace cards** (optional)
  - `frontend/reolink-recording-card.js` and `frontend/reolink-summary-card.js` are plain JS with no build step.
  - Lower priority than hassfest and Ruff.

### Suggested workflow layout

Create `.github/workflows/validate.yml` with jobs for hassfest, HACS, and Ruff (Bandit optional). Trigger on push, pull_request, and a daily schedule to catch upstream HA/hassfest changes.

### What CI will not catch

These require code changes from the security section above, not automation alone:

- Public `/local/` recording exposure
- Token redaction in debug logs
- `ssl=None` WebSocket behavior
- XSS in custom cards (ESLint can help only after rules are added)
