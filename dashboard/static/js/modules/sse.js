/* ==========================================================================
   SSE Telemetry Stream Dispatcher (API v1)
   Provides configurable real-time telemetry streaming and distribution
   ========================================================================== */

import { updateDuplicationData } from './duplication.js';
import { updateMediaSummary } from './media.js';
import { updateMountStats } from './mount.js';
import { updateStorageMatrix } from './storage.js';
import { updateVersionAndUpdates } from './updater.js';
import { updateBandwidthTelemetry } from './bandwidth.js';

let latestPayload = { transactions: [], workers: [], tailscale: {}, storage: {}, rclone: {}, summary: {}, version: null, updates: null };
let currentEvtSource = null;
let currentPollInterval = 500;

export function getLatestPayload() {
  return latestPayload;
}

export function startSSE(intervalMs = 500) {
  currentPollInterval = intervalMs;

  if (currentEvtSource) {
    currentEvtSource.close();
    currentEvtSource = null;
  }

  const pollDot = document.getElementById('header-poll-dot');

  // If paused, update dot and do not reconnect
  if (intervalMs <= 0) {
    if (pollDot) {
      pollDot.className = 'status-dot dot-gray';
      pollDot.title = 'Telemetry polling paused';
    }
    return;
  }

  if (pollDot) {
    pollDot.className = 'status-dot dot-green dot-pulse';
    pollDot.title = `Telemetry polling every ${intervalMs}ms`;
  }

  const url = `/api/v1/stream?interval=${intervalMs}`;
  currentEvtSource = new EventSource(url);

  currentEvtSource.onmessage = function(e) {
    try {
      const data = JSON.parse(e.data);
      latestPayload = data;
      dispatchTelemetry(data);
    } catch (err) {
      console.error('[SSE] JSON parse error:', err);
    }
  };

  currentEvtSource.onerror = function() {
    console.warn('[SSE] Telemetry connection disrupted, reconnecting...');
    if (pollDot) pollDot.className = 'status-dot dot-amber';
  };
}

export function setPollingInterval(intervalMs) {
  startSSE(intervalMs);
}

function dispatchTelemetry(data) {
  // 1. Version & Update Telemetry
  if (data.version || data.updates) {
    updateVersionAndUpdates(data.version, data.updates);
  }

  // 2. Simplified Header Tailscale Status Pill
  if (data.tailscale) {
    const dot = document.getElementById('header-ts-dot');
    const txt = document.getElementById('header-ts-text');
    const tb = document.getElementById('ts-badge');
    const td = document.getElementById('ts-status-desc');

    if (data.tailscale.configured) {
      if (dot) dot.className = 'status-dot dot-green';
      if (txt) txt.textContent = 'Connected';
      if (tb) {
        tb.className = 'badge badge-running';
        tb.textContent = `● Configured (${(data.tailscale.mode || 'auth_key').toUpperCase()})`;
      }
      if (td) {
        const masked = data.tailscale.masked_key || data.tailscale.masked_api || 'Active';
        td.innerHTML = `Active key: <code>${masked}</code> • Ephemeral: <strong>${data.tailscale.ephemeral ? 'Yes' : 'No'}</strong> • Auto-inject: <strong>${data.tailscale.auto_inject ? 'Enabled' : 'Disabled'}</strong>`;
      }
    } else {
      if (dot) dot.className = 'status-dot dot-gray';
      if (txt) txt.textContent = 'Not Configured';
      if (tb) {
        tb.className = 'badge badge-interrupted';
        tb.textContent = '○ Not Configured';
      }
      if (td) {
        td.textContent = 'No Tailscale key saved. Ephemeral cloud workers will run without Tailscale proxy unless supplied.';
      }
    }
  }

  // 3. Tab 1: Duplication Manager
  if (data.transactions || data.workers) {
    updateDuplicationData(data.transactions || [], data.workers || []);
  }

  // 4. Tab 2: Media & Cache Summary
  if (data.summary) {
    updateMediaSummary(data.summary);
  }

  // 5. Tab 3: Local Rclone Mount
  if (data.rclone) {
    updateMountStats(data.rclone);
  }

  // 6. Tab 4: Storage Matrix
  if (data.storage) {
    updateStorageMatrix(data.storage, data.summary);
  }

  // 7. ISP Bandwidth & Health Telemetry
  if (data.bandwidth) {
    updateBandwidthTelemetry(data.bandwidth);
  }
}
