/**
 * Reolink Summary Card for Home Assistant
 * v1.1.1
 * A custom card that pulls together all Reolink recordings,
 * sorts them by recency, and displays them dynamically.
 * Recording media is served via authenticated /api/reolink_recordings/ paths.
 */

function isSafeMediaUrl(url) {
  if (typeof url !== 'string') return false;
  const trimmed = url.trim();
  return (
    trimmed.startsWith('/') ||
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('blob:')
  );
}

/**
 * Resolve an authenticated media URL for <img>/video use.
 * /api/ paths require auth; <img> cannot send headers, so we fetch with the
 * HA access token and return a blob: URL (or a signed path for new-tab opens).
 */
async function resolveMediaUrl(hass, url, { asBlob = false } = {}) {
  if (!hass || !url || !isSafeMediaUrl(url)) return url;
  if (url.startsWith('blob:') || url.startsWith('/local/')) return url;
  if (url.includes('authSig=') && !asBlob) return url;

  const pathOnly = url.split('?')[0];

  try {
    if (asBlob && (pathOnly.startsWith('/api/') || url.startsWith('/api/'))) {
      const abs = typeof hass.hassUrl === 'function' ? hass.hassUrl(pathOnly) : pathOnly;
      const token = hass.auth && hass.auth.data && hass.auth.data.access_token;
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      const resp = await fetch(abs, { headers, credentials: 'same-origin' });
      if (!resp.ok) {
        throw new Error(`media fetch HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      return URL.createObjectURL(blob);
    }

    if (pathOnly.startsWith('/api/')) {
      const signed = await hass.callWS({ type: 'auth/sign_path', path: pathOnly });
      if (signed && signed.path) {
        return signed.path;
      }
    }
  } catch {
    // Fall through and return the original URL
  }
  return url;
}

class ReolinkSummaryCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement('reolink-summary-card-editor');
  }

  static getStubConfig() {
    return {
      title: 'Recent Activity',
      refresh_interval: 60,
      auto_discover: true,
      entities: [],
      max_items: 5,
      show_state: true,
      use_jpg: true,
      tap_action: { action: 'url' }
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._config = {};
    this._hass = null;
    this.refreshInterval = null;
    this.cardRendered = false;
  }

  setConfig(config) {
    if (!config) {
      this._config = ReolinkSummaryCard.getStubConfig();
      return;
    }
    
    this._config = {
      ...ReolinkSummaryCard.getStubConfig(),
      ...config
    };

    // Make sure we have either auto-discover or manual entities
    if (!this._config.auto_discover && (!this._config.entities || this._config.entities.length === 0)) {
      throw new Error("Please define entities or enable auto-discover");
    }
    this.cardRendered = false; // Force re-render on config change
  }

  getCardSize() {
    return 4;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._config) {
      this.render();
    }
  }

  disconnectedCallback() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
    if (this._visibilityHandler) {
      document.removeEventListener('visibilitychange', this._visibilityHandler);
      this._visibilityHandler = null;
    }
  }

  _getServerTimeZone() {
    // Pull timezone from HA runtime config — works for any installation
    if (this._hass && this._hass.config && this._hass.config.time_zone) {
      return this._hass.config.time_zone;
    }
    return null; // fallback to browser-local if unavailable
  }

  _parseRecordingDate(dateStr, timeStr) {
    if (!dateStr || !timeStr) return new Date(0);
    try {
      const dateParts = dateStr.split('/');
      const timeParts = timeStr.split(':');
      if (dateParts.length === 3 && timeParts.length === 3) {
        const y = parseInt(dateParts[0], 10);
        const mo = parseInt(dateParts[1], 10) - 1;
        const d = parseInt(dateParts[2], 10);
        const h = parseInt(timeParts[0], 10);
        const mi = parseInt(timeParts[1], 10);
        const s = parseInt(timeParts[2], 10);

        const serverTZ = this._getServerTimeZone();

        if (serverTZ) {
          // Build a naive UTC instant from the recording's date/time components.
          // This is timezone-independent — Date.UTC doesn't care about browser TZ.
          const naive = new Date(Date.UTC(y, mo, d, h, mi, s));

          // Get the server TZ offset at this instant (handles DST)
          const fmt = new Intl.DateTimeFormat('en-US', {
            timeZone: serverTZ,
            timeZoneName: 'longOffset'
          });
          const parts = fmt.formatToParts(naive);
          const tzPart = parts.find(p => p.type === 'timeZoneName');
          let offsetMinutes = 0;
          if (tzPart && tzPart.value) {
            const m = tzPart.value.match(/GMT([+-])(\d{1,2})(?::(\d{2}))?/);
            if (m) {
              offsetMinutes = (parseInt(m[2], 10) * 60 + (m[3] ? parseInt(m[3], 10) : 0));
              if (m[1] === '-') offsetMinutes = -offsetMinutes;
            }
          }

          // The recording time is in server-local time.
          // UTC = local - offset (e.g. Edmonton UTC-6: UTC = local - (-6h) = local + 6h)
          return new Date(naive.getTime() - offsetMinutes * 60000);
        } else {
          // No server TZ — fall back to browser-local parse
          return new Date(y, mo, d, h, mi, s);
        }
      }
    } catch {
      // Ignore parse failures and use fallback below
    }
    return new Date(0); // fallback
  }

  _getRecordingEntities() {
    let targetEntities = [];
    if (this._config.auto_discover) {
      // Find all sensor entities ending with _latest_recording
      targetEntities = Object.keys(this._hass.states).filter(entityId => 
        entityId.startsWith('sensor.') && (entityId.includes('_latest_recording'))
      );
    }
    // Always merge any explicitly configured entities
    for (const entityId of (this._config.entities || [])) {
      if (entityId && !targetEntities.includes(entityId)) {
        targetEntities.push(entityId);
      }
    }

    const validRecordings = [];

    targetEntities.forEach(entityId => {
      const stateObj = this._hass.states[entityId];
      if (!stateObj) return;

      const attrs = stateObj.attributes;
      // Skip if missing critical info (file_name indicates a recording is available)
      if (!attrs || (!attrs.file_name && !attrs.media_url && !attrs.file_path)) return;

      const recDate = this._parseRecordingDate(attrs.date, attrs.timestamp);
      
      const entityName = entityId.split('.')[1].replace(/_/g, ' ');
      const friendlyName = attrs.friendly_name || entityName;

      validRecordings.push({
        entityId: entityId,
        dateObj: recDate,
        attributes: attrs,
        name: friendlyName
      });
    });

    // Sort descending by actual recording time
    validRecordings.sort((a, b) => b.dateObj.getTime() - a.dateObj.getTime());

    // Limit if needed
    const maxItems = this._config.max_items || 5;
    return validRecordings.slice(0, maxItems);
  }

  _getImageUrl(attrs) {
    let baseUrl = '';
    if (this._config.use_jpg && attrs.jpg_picture) {
      baseUrl = attrs.jpg_picture;
    } else if (attrs.entity_picture) {
      baseUrl = attrs.entity_picture;
    } else {
      return null;
    }
    // entity_picture already includes a cache-buster (?t=...); don't duplicate it
    if (baseUrl.includes('?')) {
      return baseUrl;
    }
    return `${baseUrl}?t=${Date.now()}`;
  }

  _getVideoUrl(attrs) {
    if (!attrs.media_url) return null;
    // Keep path only for signing/fetch; cache-buster is unused for blob/signed opens
    return attrs.media_url.split('?')[0];
  }

  _renderEmptyState() {
    this.shadowRoot.innerHTML = `
      <style>
        .empty-message {
          padding: 16px;
          color: var(--secondary-text-color);
        }
        .title {
          padding: 16px 16px 8px 16px;
          font-size: 1.2rem;
          font-weight: 500;
          color: var(--primary-text-color);
        }
      </style>
      <ha-card id="summary-card"></ha-card>
    `;
    const card = this.shadowRoot.getElementById('summary-card');
    if (card && this._config.title) {
      const titleEl = document.createElement('div');
      titleEl.className = 'title';
      titleEl.textContent = this._config.title;
      card.appendChild(titleEl);
    }
    if (card) {
      const message = document.createElement('div');
      message.className = 'empty-message';
      message.textContent = 'No recordings found. Ensure auto-discovery is enabled or entities are specified.';
      card.appendChild(message);
    }
  }

  render() {
    if (!this._hass || !this._config) return;

    const recordings = this._getRecordingEntities();
    
    if (recordings.length === 0) {
      this._renderEmptyState();
      // Keep cardRendered false so a later hass update can build the real layout
      this.cardRendered = false;
      return;
    }

    const hasLayout = Boolean(this.shadowRoot.getElementById('recordings-container'));
    if (!this.cardRendered || !hasLayout) {
      this.shadowRoot.innerHTML = `
        <style>
          ha-card {
            overflow: hidden;
            display: flex;
            flex-direction: column;
          }
          .title {
            padding: 16px 16px 8px 16px;
            font-size: 1.2rem;
            font-weight: 500;
            color: var(--primary-text-color);
          }
          
          .grid-container {
            display: flex;
            flex-direction: column;
            gap: 12px;
            padding: 0 16px 16px 16px;
          }
          
          .hero-item {
            position: relative;
            width: 100%;
            border-radius: 8px;
            overflow: hidden;
            cursor: pointer;
            aspect-ratio: 16/9;
            background: #000;
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
          }
          
          .secondary-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
          }
          
          .secondary-item {
            position: relative;
            width: 100%;
            border-radius: 6px;
            overflow: hidden;
            cursor: pointer;
            min-height: 80px;
            background: #222;
            opacity: 0.9;
            transition: opacity 0.2s;
            box-shadow: 0 1px 3px rgba(0,0,0,0.15);
          }
          
          .secondary-item:hover {
            opacity: 1;
          }
          
          img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
          }
          
          .overlay-bottom {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 60%, transparent 100%);
            color: white;
            padding: 12px;
            display: flex;
            flex-direction: column;
            z-index: 5;
          }
          
          .hero-item .overlay-bottom {
            padding: 16px;
          }
          
          .secondary-item .overlay-bottom {
            padding: 8px;
            font-size: 0.85em;
          }
          
          .cam-name {
            font-weight: 600;
            margin-bottom: 2px;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
          }
          .hero-item .cam-name {
             font-size: 1.1em;
          }
          
          .event-meta {
            display: flex;
            justify-content: space-between;
            color: #ddd;
            font-size: 0.9em;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.8);
          }
          .secondary-item .event-meta {
             font-size: 0.8em;
          }
          
          .play-icon {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            opacity: 0;
            background-color: rgba(0, 0, 0, 0.5);
            border-radius: 50%;
            width: 48px;
            height: 48px;
            display: flex;
            justify-content: center;
            align-items: center;
            transition: opacity 0.3s;
            z-index: 10;
          }
          .secondary-item .play-icon {
            width: 32px;
            height: 32px;
          }
          .hero-item:hover .play-icon, .secondary-item:hover .play-icon {
            opacity: 1;
          }
          .play-icon svg {
            width: 28px;
            height: 28px;
            fill: white;
          }
          .secondary-item .play-icon svg {
            width: 18px;
            height: 18px;
          }
          .live-btn {
            position: absolute;
            top: 8px;
            left: 8px;
            background: rgba(0, 0, 0, 0.6);
            color: #ddd;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 500;
            z-index: 10;
            backdrop-filter: blur(2px);
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            border: 1px solid rgba(255,255,255,0.2);
            transition: all 0.2s ease;
          }
          .secondary-item .live-btn {
            top: 6px;
            left: 6px;
            padding: 4px 6px;
            border-radius: 4px;
            border: none;
            background: rgba(0, 0, 0, 0.45);
          }
          .secondary-item .live-btn span {
            display: none; /* Hide the text "Live View" on small cards to save space */
          }
          .live-btn:hover {
            background: rgba(30, 30, 30, 0.9);
            color: white;
            border-color: rgba(255,255,255,0.5);
            transform: scale(1.05);
          }
          .secondary-item .live-btn:hover {
            background: rgba(0, 0, 0, 0.8);
          }
          .live-icon svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
          }
          .relative-time {
             position: absolute;
             top: 8px;
             right: 8px;
             background: rgba(0, 0, 0, 0.6);
             color: white;
             padding: 4px 8px;
             border-radius: 4px;
             font-size: 0.8rem;
             z-index: 5;
             backdrop-filter: blur(2px);
          }
          .secondary-item .relative-time {
             top: 6px;
             right: 6px;
             font-size: 0.65rem;
             padding: 3px 6px;
             background: rgba(0, 0, 0, 0.45);
          }
          .secondary-item .overlay-bottom {
             padding: 8px;
          }
          .secondary-item .cam-name {
             font-size: 0.9em;
             white-space: nowrap;
             overflow: hidden;
             text-overflow: ellipsis;
             margin-bottom: 0px;
          }
          .secondary-item .event-meta {
             font-size: 0.75em;
          }
        </style>


        <ha-card id="summary-card">
          <div class="grid-container" id="recordings-container">
             <!-- Content injected dynamically -->
          </div>
        </ha-card>
      `;

      const card = this.shadowRoot.getElementById('summary-card');
      if (card && this._config.title) {
        const titleEl = document.createElement('div');
        titleEl.className = 'title';
        titleEl.textContent = this._config.title;
        card.insertBefore(titleEl, card.firstChild);
      }

      this.cardRendered = true;
      this.setupAutoRefresh();
    }

    this._updateContent(recordings);
  }

  _timeSince(dateObj) {
    const now = new Date();
    const seconds = Math.floor((now - dateObj) / 1000);
    let interval = seconds / 31536000;
    if (interval > 1) return Math.floor(interval) + " years ago";
    interval = seconds / 2592000;
    if (interval > 1) return Math.floor(interval) + " months ago";
    interval = seconds / 86400;
    if (interval > 1) return Math.floor(interval) + " days ago";
    interval = seconds / 3600;
    if (interval > 1) return Math.floor(interval) + " hours ago";
    interval = seconds / 60;
    if (interval > 1) return Math.floor(interval) + " mins ago";
    return Math.floor(seconds > 0 ? seconds : 0) + " secs ago";
  }
  
  _findLiveCamera(cameraName) {
    if (!this._hass || !this._hass.states || !cameraName) return null;
    const target = cameraName.toLowerCase();
    
    const cameras = Object.keys(this._hass.states).filter(c => c.startsWith('camera.'));
    
    // Find cameras that have a matching friendly name or entity ID
    const matches = cameras.filter(entityId => {
      const attrs = this._hass.states[entityId].attributes || {};
      const friendlyObj = (attrs.friendly_name || entityId).toLowerCase();
      return friendlyObj.includes(target) || entityId.includes(target.replace(/ /g, '_'));
    });
    
    // Prefer higher quality stream
    const clear = matches.find(c => {
         const attrs = this._hass.states[c].attributes || {};
         return (attrs.friendly_name || c).toLowerCase().includes('clear') || c.includes('clear') || c.includes('main');
    });
    if (clear) return clear;
    
    const fluency = matches.find(c => {
         const attrs = this._hass.states[c].attributes || {};
         return (attrs.friendly_name || c).toLowerCase().includes('fluent') || c.includes('fluent') || c.includes('sub');
    });
    if (fluency) return fluency;
    
    return matches.length > 0 ? matches[0] : null;
  }

  _createPlayIcon() {
    const playIcon = document.createElement('div');
    playIcon.className = 'play-icon';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M8,5.14V19.14L19,12.14L8,5.14Z');
    svg.appendChild(path);
    playIcon.appendChild(svg);
    return playIcon;
  }

  _createLiveButton(index) {
    const liveBtn = document.createElement('div');
    liveBtn.className = 'live-btn';
    liveBtn.id = `live-${index}`;
    liveBtn.title = 'View Live Camera';

    const liveIcon = document.createElement('div');
    liveIcon.className = 'live-icon';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute(
      'd',
      'M17,10.5V7A1,1 0 0,0 16,6H4A1,1 0 0,0 3,7V17A1,1 0 0,0 4,18H16A1,1 0 0,0 17,17V13.5L21,17.5V6.5L17,10.5Z'
    );
    svg.appendChild(path);
    liveIcon.appendChild(svg);
    liveBtn.appendChild(liveIcon);

    const label = document.createElement('span');
    label.textContent = 'View Live';
    liveBtn.appendChild(label);
    return liveBtn;
  }

  _createRecordingItem(rec, index, isHero) {
    const imageUrl = this._getImageUrl(rec.attributes);
    const videoUrl = this._getVideoUrl(rec.attributes);
    const eventType = rec.attributes.event_type || 'Motion';
    const timestamp = rec.attributes.timestamp || '';
    const timeAgo = this._timeSince(rec.dateObj);

    let cleanName = rec.name.replace(/latest recording/i, '').replace(/_latest_recording/i, '').trim();
    if (!cleanName) {
      cleanName = rec.entityId.replace('sensor.', '').replace('_latest_recording', '');
    }

    if (cleanName.includes('_')) {
      cleanName = cleanName.split('_')
        .filter(Boolean)
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    } else if (cleanName === cleanName.toLowerCase()) {
      cleanName = cleanName.charAt(0).toUpperCase() + cleanName.slice(1);
    }

    const cameraEntity = this._findLiveCamera(cleanName);
    const item = document.createElement('div');
    item.className = isHero ? 'hero-item' : 'secondary-item';
    item.id = `rec-${index}`;

    if (cameraEntity) {
      item.appendChild(this._createLiveButton(index));
    }

    const relativeTime = document.createElement('div');
    relativeTime.className = 'relative-time';
    relativeTime.textContent = timeAgo;
    item.appendChild(relativeTime);

    if (imageUrl && isSafeMediaUrl(imageUrl)) {
      const img = document.createElement('img');
      img.alt = cleanName;
      img.loading = 'lazy';
      item.appendChild(img);
      resolveMediaUrl(this._hass, imageUrl, { asBlob: true }).then((signed) => {
        if (signed && isSafeMediaUrl(signed)) {
          if (img.dataset.blobUrl) {
            URL.revokeObjectURL(img.dataset.blobUrl);
          }
          if (signed.startsWith('blob:')) {
            img.dataset.blobUrl = signed;
          }
          img.src = signed;
        }
      });
    } else {
      const placeholder = document.createElement('div');
      placeholder.style.height = '100%';
      placeholder.style.display = 'flex';
      placeholder.style.alignItems = 'center';
      placeholder.style.justifyContent = 'center';
      placeholder.style.color = '#ccc';
      placeholder.textContent = 'No Image';
      item.appendChild(placeholder);
    }

    const overlay = document.createElement('div');
    overlay.className = 'overlay-bottom';

    const camName = document.createElement('div');
    camName.className = 'cam-name';
    camName.textContent = cleanName;
    overlay.appendChild(camName);

    const eventMeta = document.createElement('div');
    eventMeta.className = 'event-meta';

    const eventTypeEl = document.createElement('span');
    eventTypeEl.textContent = eventType;
    eventMeta.appendChild(eventTypeEl);

    const timestampEl = document.createElement('span');
    timestampEl.textContent = timestamp;
    eventMeta.appendChild(timestampEl);

    overlay.appendChild(eventMeta);
    item.appendChild(overlay);
    item.appendChild(this._createPlayIcon());

    if (videoUrl) {
      item.addEventListener('click', () => {
        resolveMediaUrl(this._hass, videoUrl, { asBlob: false }).then((signed) => {
          this._openModal(signed, cleanName, timestamp);
        });
      });
    }

    const liveEl = item.querySelector(`#live-${index}`);
    if (liveEl && cameraEntity) {
      liveEl.addEventListener('click', (event) => {
        event.stopPropagation();
        this.dispatchEvent(new CustomEvent('hass-more-info', {
          detail: { entityId: cameraEntity },
          bubbles: true,
          composed: true,
        }));
      });
    }

    return item;
  }

  _updateContent(recordings) {
    const container = this.shadowRoot.getElementById('recordings-container');
    if (!container) return;

    container.replaceChildren();

    let secondaryGrid = null;

    recordings.forEach((rec, index) => {
      const isHero = index === 0;
      const item = this._createRecordingItem(rec, index, isHero);

      if (isHero) {
        container.appendChild(item);
        if (recordings.length > 1) {
          secondaryGrid = document.createElement('div');
          secondaryGrid.className = 'secondary-grid';
          container.appendChild(secondaryGrid);
        }
      } else if (secondaryGrid) {
        secondaryGrid.appendChild(item);
      } else {
        container.appendChild(item);
      }
    });
  }

  _openModal(url, title, timestamp) {
    if (!url || !isSafeMediaUrl(url)) return;
    
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.85); z-index: 999999; display: flex; flex-direction: column; justify-content: center; align-items: center; font-family: var(--paper-font-common-base_-_font-family, sans-serif); opacity: 0; transition: opacity 0.3s ease;';
    
    wrapper.onclick = (e) => {
      if (e.target === wrapper) this._closeModal(wrapper);
    };
    
    // Close button
    const closeBtn = document.createElement('div');
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = 'position: absolute; top: 20px; right: 20px; color: white; font-size: 28px; cursor: pointer; background: rgba(255,255,255,0.2); width: 48px; height: 48px; border-radius: 50%; text-align: center; line-height: 48px; z-index: 2;';
    closeBtn.onmouseover = () => closeBtn.style.background = 'rgba(255,255,255,0.4)';
    closeBtn.onmouseout = () => closeBtn.style.background = 'rgba(255,255,255,0.2)';
    closeBtn.onclick = () => this._closeModal(wrapper);
    
    // Container
    const container = document.createElement('div');
    container.style.cssText = 'width: 90%; max-width: 1000px; background: black; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.6); z-index: 1; transform: scale(0.95); transition: transform 0.3s ease;';
    
    // Header
    const header = document.createElement('div');
    header.style.cssText = 'color: white; padding: 16px 20px; font-size: 1.2rem; background: #1a1a1a; display: flex; justify-content: space-between; border-bottom: 1px solid #333;';

    const titleSpan = document.createElement('span');
    titleSpan.textContent = title;
    header.appendChild(titleSpan);

    const timestampSpan = document.createElement('span');
    timestampSpan.style.color = '#aaa';
    timestampSpan.style.fontSize = '1rem';
    timestampSpan.textContent = timestamp;
    header.appendChild(timestampSpan);
    
    // Video
    const video = document.createElement('video');
    video.controls = true;
    video.autoplay = true;
    video.playsInline = true;
    video.style.cssText = 'width: 100%; display: block; max-height: calc(100vh - 120px); object-fit: contain; background: black; outline: none;';
    
    const source = document.createElement('source');
    source.src = url;
    source.type = 'video/mp4';
    
    video.appendChild(source);
    container.appendChild(header);
    container.appendChild(video);
    wrapper.appendChild(closeBtn);
    wrapper.appendChild(container);
    
    document.body.appendChild(wrapper);
    
    // Animate in
    requestAnimationFrame(() => {
      wrapper.style.opacity = '1';
      container.style.transform = 'scale(1)';
    });
  }

  _closeModal(wrapper) {
    if (!wrapper || !wrapper.parentNode) return;
    wrapper.style.opacity = '0';
    wrapper.children[1].style.transform = 'scale(0.95)';
    setTimeout(() => {
      if (wrapper.parentNode) {
        document.body.removeChild(wrapper);
      }
    }, 300);
  }

  setupAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
    const refreshSeconds = parseInt(this._config.refresh_interval) || 60;
    if (refreshSeconds > 0) {
      this.refreshInterval = setInterval(() => {
        if (document.visibilityState === 'visible') {
           this.render(); // Re-fetch logic and re-render completely to check new sorting
        }
      }, refreshSeconds * 1000);
      
      if (!this._visibilityHandler) {
        this._visibilityHandler = () => {
          if (document.visibilityState === 'visible') {
            this.render();
          }
        };
        document.addEventListener('visibilitychange', this._visibilityHandler);
      }
    }
  }
}

// Basic Editor Stub just so it doesn't crash if they try to edit it via UI
class ReolinkSummaryCardEditor extends HTMLElement {
  setConfig(config) { this._config = config; }
  set hass(hass) {}
  render() { 
    this.textContent = 'Summary Card configuration currently requires YAML. Auto discovery will automatically pull in all your Reolink sensors.';
  }
}

customElements.define('reolink-summary-card-editor', ReolinkSummaryCardEditor);
customElements.define('reolink-summary-card', ReolinkSummaryCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: 'reolink-summary-card',
  name: 'Reolink Summary Card',
  preview: true,
  description: 'Displays a timeline sequence of Reolink recent recordings.',
});
