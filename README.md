# Reolink Recordings for Home Assistant

A custom component that fetches and downloads the latest recordings from your **Reolink Home Hub** (which stores recordings from Reolink battery-powered cameras), making them available as media sources in Home Assistant dashboards.

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

## Installation

### Manual Installation
1. Download the repository as a ZIP file and extract it
2. Copy the `reolink_recordings` folder to your Home Assistant `custom_components` directory
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
   - Username: Your Home Assistant username (not used yet)
   - Password: Your Home Assistant Long-Lived Access Token
     - Create one at your profile page → Long-Lived Access Tokens

### Configuration Options
After setup, you can adjust these options:
- Scan Interval: How often to check for new recordings (in minutes)
- Storage Path: Where to store downloaded recordings (default: `reolink_recordings`, under your HA config directory — do **not** use a path under `www/`, which is publicly accessible)
- Snapshot Format: Choose between animated GIF, static JPG, or both for snapshots
- Enable Caching: Toggle the caching system on/off (useful to disable during development/debugging)
- Resolution Preference: Choose between high-resolution (default) or low-resolution streams when browsing recordings

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

1. Copy the `reolink-recording-card.js` file to your `www` directory
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

1. Copy the `reolink-summary-card.js` file to your `www` directory
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

The integration provides these services:

#### reolink_recordings.fetch_latest_recordings
Manually triggers a refresh of all recordings stored on the Home Hub.

#### reolink_recordings.download_recording
Downloads a recording from the Home Hub for a specific camera.

Parameters:
- `camera_name`: Name of the camera
- `entity_id`: Optional, the entity ID of this integration

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

Pull requests and pushes run GitHub Actions (`.github/workflows/validate.yml`) with three jobs:

- **hassfest** — validates `manifest.json`, translations, config flow, and `services.yaml`
- **ruff** — Python linting
- **eslint** — Lovelace card linting in `frontend/`

The workflow also runs nightly to catch upstream Home Assistant rule changes.

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
