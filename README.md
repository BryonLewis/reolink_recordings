# Reolink Recordings for Home Assistant

Repository: [github.com/BryonLewis/reolink_recordings](https://github.com/BryonLewis/reolink_recordings)

A custom component that fetches and downloads the latest recordings from your **Reolink Home Hub** (which stores recordings from Reolink battery-powered cameras), making them available as media sources in Home Assistant dashboards.

Originally created by [@rcourtna](https://github.com/rcourtna); maintained by [@BryonLewis](https://github.com/BryonLewis).

> **IMPORTANT**: This component only works with the **Reolink Home Hub** device and does not interact with Reolink cameras directly. The component interfaces with the Home Hub to access recordings that were previously captured and stored on the hub.

## Features

- Automatically discovers and downloads the latest recordings stored in your Reolink Home Hub from connected battery-powered cameras
- Makes recordings available via Home Assistant's authenticated media source (requires login)
- Creates sensors with attributes containing recording details
- Detects specific event types (Motion, Person, Vehicle, Animal) from recording metadata
- Uses fixed filenames for latest recordings to simplify dashboard usage
- Enables auto-refreshing images on your dashboard
- Provides tap-to-expand functionality for quick viewing
- Generates high-quality animated GIF previews (640px width) and JPG snapshots (1024px width)
- Intelligent caching system to avoid redundant downloads of identical recordings
- Prepares downloaded recordings for future AI processing
- Periodic update of recordings (configurable interval)
- Optional event-driven discovery via mapped motion sensors
- Device triggers and `reolink_recordings_updated` events for automations
- Admin-only `reolink_recordings.refresh` service for on-demand updates

## Installation

### Manual Installation
1. Download the [repository](https://github.com/BryonLewis/reolink_recordings) as a ZIP file and extract it
2. Copy the `custom_components/reolink_recordings` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

> **Note:** HACS installation is not yet available for this component. It will be added in a future release.

## Configuration

### Through the UI
1. Go to Settings → Devices & Services
2. Click "+ Add Integration" button at the bottom right
3. Search for "Reolink Recordings" (after installing the component and restarting Home Assistant, it will appear in the integration list)
4. Follow the configuration steps:
   - Name: A name for this integration
   - Host: Your Home Assistant URL (default: http://localhost:8123)
   - Access Token: Your Home Assistant Long-Lived Access Token
     - Create one at your profile page → Long-Lived Access Tokens

### Configuration Options
After setup, you can adjust these options:
- Scan Interval: How often to check for new recordings (in minutes). Used for periodic discovery even when event-driven mode is enabled.
- Storage Path: Where to store downloaded recordings (default: `reolink_recordings` under your HA config directory). Absolute paths are allowed (e.g. `/media/reolink_recordings` or a NAS mount). Avoid `www/`, which is publicly accessible without login — a warning is logged if you use it.
- Snapshot Format: Choose between animated GIF, static JPG, or both for snapshots
- Enable Caching: Toggle the caching system on/off (useful to disable during development/debugging)
- Resolution Preference: Choose between high-resolution (default) or low-resolution streams when browsing recordings
- Enable Event-Driven Discovery: When enabled, motion sensors can trigger a targeted discovery for the mapped camera instead of waiting for the next scan interval (default: on)
- Upload Delay: Seconds to wait after motion before checking the Home Hub for a new recording (default: 30; range 5–300). Gives the hub time to finish uploading.

#### Event-driven discovery

Periodic scans and event-driven discovery work together:

1. **Periodic scan** (`scan_interval`) walks all cameras on a timer and downloads any new latest recordings.
2. **Event-driven discovery** listens to mapped motion sensors. When motion clears, the integration waits `upload_delay` seconds, then discovers and downloads only that camera’s latest recording.
3. **Manual refresh** (`reolink_recordings.refresh`) runs a full refresh of all cameras on demand (admin-only).

When event-driven discovery is enabled in the options UI, a second step lets you map each motion sensor entity to a Home Hub camera. Choose **none** to leave a sensor unmapped. Without mappings, event-driven mode does nothing until you configure them.

## Usage

### Adding Home Hub recordings to your dashboard

#### Method 1: Using the Picture Entity card (auto-refreshing)
This method will show the latest recording frame and auto-refresh it.

1. Go to your dashboard
2. Add a new card → Picture Entity
3. Configure with these settings:

```yaml
type: picture-entity
entity: sensor.camera_name_latest_recording
camera_view: auto
show_state: true
show_name: true
tap_action:
  action: url
  url_path: /api/sensor/sensor.camera_name_latest_recording/attribute/media_url
```

Replace:
- `camera_name` with your camera's name (as it appears in the sensor name)

#### Method 2: Using Picture Card with Auto-Refresh

This method displays an auto-refreshing snapshot from the latest recording with a tap-to-expand functionality:

```yaml
type: picture
image: /api/sensor/sensor.front_door_latest_recording/attribute/entity_picture
refresh_interval: 60
tap_action:
  action: fire-dom-event
  browser_mod:
    service: browser_mod.popup
    data:
      content:
        type: picture
        image: /api/sensor/sensor.front_door_latest_recording/attribute/entity_picture
        tap_action:
          action: none
      title: Front Door Camera
      size: wide
      autoclose: false
```

Replace `front_door` with your camera's name (as it appears in the sensor name).

This method:
- Auto-refreshes every 60 seconds
- Shows the latest recording frame
- Pops up a larger view when tapped
- Requires the [browser_mod](https://github.com/thomasloven/hass-browser_mod) integration

#### Method 3: Alternative Picture Card (No browser_mod needed)

```yaml
type: picture
image: /api/sensor/sensor.front_door_latest_recording/attribute/entity_picture
refresh_interval: 60
tap_action:
  action: url
  url_path: /api/sensor/sensor.front_door_latest_recording/attribute/media_url
```

This will open the recording in your browser when tapped.

#### Method 4: Using the Custom Reolink Recording Card (Recommended)

A custom Lovelace card has been created specifically for this integration and provides the best experience:

1. Copy `custom_components/reolink_recordings/frontend/reolink-recording-card.js` to your `www` directory
2. Add it as a resource in your Lovelace configuration:
   - Go to Settings → Dashboards → Resources
   - Add `/local/reolink-recording-card.js` as a JavaScript module
3. Add the card to your dashboard:

```yaml
type: custom:reolink-recording-card
entity: sensor.first_landing_latest_recording
title: First Landing
refresh_interval: 60
show_title: true
show_state: true
use_jpg: true
tap_action:
  action: url
```

#### Method 5: Using the Reolink Summary Card (Timeline View)

The Reolink Summary Card provides a consolidated, timeline-based view of all your Reolink cameras. It automatically discovers all your `sensor.*_latest_recording` entities and sorts them by recency, featuring a "Hero" layout for the most recent event.

1. Copy `custom_components/reolink_recordings/frontend/reolink-summary-card.js` to your `www` directory
2. Add it as a resource in your Lovelace configuration:
   - Go to Settings → Dashboards → Resources
   - Add `/local/reolink-summary-card.js` as a JavaScript module
3. Add the card to your dashboard:

```yaml
type: custom:reolink-summary-card
title: Recent Activity
```

Features:
- **Auto-Discovery**: Automatically detects all Reolink recording sensors in your system.
- **Smart Sorting**: Always puts the most recent recording front and center as a "Hero" item.
- **Timeline Layout**: Displays older recordings in a secondary grid below the hero.
- **Relative Time**: Shows "3 minutes ago", "1 hour ago", etc. for quick context.
- **Performance Optimized**: Uses `IntersectionObserver` to only refresh when the card is visible.
- **Click to Play**: Tapping any recording opens the MP4 video in a new tab.

### Services

#### `reolink_recordings.refresh`

Admin-only service that fetches and downloads the latest recordings from the Home Hub for all cameras (same work as a scheduled scan).

| Field | Required | Description |
|-------|----------|-------------|
| `entry_id` | No | Config entry to refresh. When omitted, refreshes every loaded entry. |

```yaml
service: reolink_recordings.refresh
data: {}
```

```yaml
service: reolink_recordings.refresh
data:
  entry_id: "0123456789abcdef0123456789abcdef"
```

### Device triggers and events

Each camera device exposes these [device triggers](https://www.home-assistant.io/docs/automation/trigger/#device-triggers) (also available under **Automations → Add trigger → Device**):

| Trigger | When it fires |
|---------|----------------|
| New recording available (`recording_updated`) | Any new/updated recording for that camera |
| Vehicle detected (`vehicle_detected`) | Recording event type contains “vehicle” |
| Person detected (`person_detected`) | Recording event type contains “person” |
| Motion detected (`motion_detected`) | Motion event that is not vehicle or person |

These triggers listen for the `reolink_recordings_updated` bus event. You can also use that event directly:

```yaml
trigger:
  - platform: event
    event_type: reolink_recordings_updated
```

Event data may include: `camera`, `event_type`, `date`, `timestamp`, `duration`, `recording_id`, and `file_path`.

#### Example: notify when a person is detected

Configure via the UI with a device trigger, or in YAML (replace `device_id` with your camera device id from Developer Tools → Devices):

```yaml
alias: Notify on person recording
trigger:
  - platform: device
    domain: reolink_recordings
    device_id: YOUR_CAMERA_DEVICE_ID
    type: person_detected
action:
  - service: notify.persistent_notification
    data:
      message: "Person detected on {{ trigger.event.data.camera }}"
```

#### Example: manual refresh on a schedule

```yaml
alias: Nightly Reolink refresh
trigger:
  - platform: time
    at: "03:00:00"
action:
  - service: reolink_recordings.refresh
    data: {}
```

## Sensor Data and Attributes

For each camera connected to your Home Hub, this integration creates a sensor entity with the format `sensor.camera_name_latest_recording` that provides useful data:

### Sensor State
The sensor state combines the recording date, timestamp, and event type in a format like:
```
2025/7/20 17:21:21 - Motion Person
```

### Available Attributes
Each sensor has these attributes:
- `date`: The recording date (e.g., "2025/7/20")
- `timestamp`: The recording time (e.g., "17:21:21")
- `duration`: The recording duration (e.g., "0:00:12")
- `event_type`: The detected event type (e.g., "Motion", "Motion Person", "Vehicle", "Animal")
- `file_path`: Full path to the recording file
- `file_name`: Name of the recording file
- `media_url`: Authenticated URL to access the MP4 recording (via `/media-source/reolink_recordings/...`)
- `entity_picture`: Authenticated URL to the snapshot image (GIF or JPG based on configuration)
- `jpg_picture`: Authenticated URL to the JPG snapshot (when using both GIF and JPG format)

These attributes can be used in automations, templates, and dashboard cards.

## Viewing Recordings

Recordings are stored under `<config>/reolink_recordings/recordings/` by default (outside the public `www/` directory). They are served through Home Assistant's authenticated media source at `/media-source/reolink_recordings/...`, so only logged-in users can access surveillance footage.

Each connected camera has fixed filenames for the latest recording (`camera_name_latest.mp4`), animated preview (`camera_name_latest.gif`), and snapshot (`camera_name_latest.jpg`) for easy reference in dashboards and automations.

### Upgrading from earlier versions

If you previously used `www/reolink_recordings` as the storage path, update the integration option to `reolink_recordings` (or another path outside `www/`), move any existing files from `www/reolink_recordings/recordings/` to the new location, and restart Home Assistant. Existing installs are migrated automatically on upgrade, but files must be moved manually or re-downloaded via a refresh.

## Performance Optimizations

### Caching System
The integration includes an intelligent caching system that avoids redundant downloads of identical recordings. Each recording is assigned a unique ID based on camera index, timestamp, event type, and duration. When a recording with the same ID is detected, the download is skipped, reducing network traffic and CPU usage.

You can disable caching in the integration options when debugging or developing new features.

## Development

Pull requests run GitHub Actions (`.github/workflows/validate.yml`) with three jobs:

- **hassfest** — validates `manifest.json`, translations, config flow, and `services.yaml`
- **ruff** — Python linting
- **eslint** — Lovelace card linting in `custom_components/reolink_recordings/frontend/`

### Run checks locally

**Python (Ruff):**

```bash
pip install ruff
ruff check .
```

**JavaScript (ESLint):**

```bash
npm install
npm run lint
```

**Home Assistant validation (hassfest):**

Hassfest runs in CI via Docker. To run it locally:

```bash
docker run --rm -v "${PWD}://github/workspace" ghcr.io/home-assistant/hassfest
```

On Windows PowerShell, use `$PWD.Path` instead of `$PWD` in the volume mount if needed.

## Attribution

This integration was originally developed by [@rcourtna](https://github.com/rcourtna). The current repository and ongoing maintenance are by [@BryonLewis](https://github.com/BryonLewis).
