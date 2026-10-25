/* ==========================================================================
   Local Rclone Mount Controller (Tab 3)
   Manages sparkline, queue context metrics, segmented transfers table,
   file path formatting, and mount throttling controls
   ========================================================================== */

import { reconcileList, bindText, bindStyle, getBoundElement } from './dom.js';
import { escapeHtml, formatIsoRelativeTime, getMediaIcon } from './formatters.js';
import * as api from './api.js';

// Sparkline Rolling Bandwidth History (Last 60 Points / ~30-60 Seconds)
const SPARKLINE_POINTS = 60;
const speedHistory = new Array(SPARKLINE_POINTS).fill(0);

// Active View: 'active' | 'recent' | 'failed'
let currentView = 'active';
let lastRcloneData = null;

export function getTransfersView() {
  return currentView;
}

export function setTransfersView(view) {
  currentView = view;
  const buttons = document.querySelectorAll('#transfers-view-toggle .seg-btn');
  buttons.forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });
  if (lastRcloneData) {
    renderTransfersTable(lastRcloneData);
  }
}

export async function toggleMountPause() {
  if (!lastRcloneData) return;
  const isCurrentlyPaused = lastRcloneData.is_paused || false;
  const targetRate = isCurrentlyPaused ? 'off' : '1B';
  try {
    const btn = document.getElementById('btn-toggle-pause');
    if (btn) btn.disabled = true;
    await api.throttleMount(targetRate);
    lastRcloneData.is_paused = !isCurrentlyPaused;
    updatePauseButtonState(lastRcloneData.is_paused);
  } catch (err) {
    alert('Failed to toggle upload bandwidth: ' + err);
  } finally {
    const btn = document.getElementById('btn-toggle-pause');
    if (btn) btn.disabled = false;
  }
}

function updatePauseButtonState(isPaused) {
  const iconEl = document.getElementById('pause-btn-icon');
  const textEl = document.getElementById('pause-btn-text');
  const btn = document.getElementById('btn-toggle-pause');

  if (iconEl) iconEl.textContent = isPaused ? '▶' : '⏸';
  if (textEl) textEl.textContent = isPaused ? 'Resume Uploads' : 'Pause Uploads';
  if (btn) {
    btn.title = isPaused ? 'Click to resume normal upload bandwidth' : 'Click to pause/throttle cloud uploads';
    if (isPaused) {
      btn.classList.add('btn-amber');
    } else {
      btn.classList.remove('btn-amber');
    }
  }
}

export function updateMountStats(rclone) {
  if (!rclone) return;
  lastRcloneData = rclone;

  // 1. KPI Card 1: Speed & Sparkline
  const elSpeed = document.getElementById('stat-rc-speed');
  if (elSpeed) {
    elSpeed.textContent = rclone.speed || '0 B/s';
    const isIdle = !rclone.speed || rclone.speed === '0 B/s' || rclone.speed === '0.0 B/s';
    elSpeed.style.color = isIdle ? 'var(--text-muted)' : 'var(--green-light)';
  }

  const liveBps = rclone.speed_bps || 0;
  updateSparkline(liveBps);

  // 2. KPI Card 2: Active Uploads & Queue Depth
  const elActive = document.getElementById('stat-rc-active');
  const elQueue = document.getElementById('stat-rc-queue');
  const elRemaining = document.getElementById('stat-rc-remaining');

  if (elActive) elActive.textContent = rclone.transfers_active || 0;
  if (elQueue) elQueue.textContent = `${rclone.uploads_queued || 0} queued`;
  if (elRemaining) elRemaining.textContent = `(${rclone.remaining_bytes_str || '0 B'} remaining)`;

  // 3. KPI Card 3: Transfers Completed & Errors
  const elDone = document.getElementById('stat-rc-done');
  const elCommitted = document.getElementById('stat-rc-committed');
  const elFailed = document.getElementById('stat-rc-failed');

  if (elDone) elDone.textContent = rclone.transfers_done || 0;
  if (elCommitted) elCommitted.textContent = `${rclone.transfers_done || 0} committed`;
  if (elFailed) {
    const failedCount = rclone.transfers_failed || 0;
    elFailed.textContent = `${failedCount} failed`;
    if (failedCount > 0) {
      elFailed.style.color = 'var(--amber)';
      elFailed.style.fontWeight = '600';
    } else {
      elFailed.style.color = 'var(--text-muted)';
      elFailed.style.fontWeight = 'normal';
    }
  }

  // 4. KPI Card 4: Total Uploaded (Session Monotonic)
  const elTotal = document.getElementById('stat-rc-total');
  if (elTotal) elTotal.textContent = rclone.total_uploaded || '0 B';

  // 5. Global Pause Toggle Button State
  updatePauseButtonState(rclone.is_paused || false);

  // 6. Update Segmented Control Counters
  const countActive = document.getElementById('count-active');
  const countRecent = document.getElementById('count-recent');
  const countFailed = document.getElementById('count-failed');

  if (countActive) countActive.textContent = (rclone.jobs || []).length;
  if (countRecent) countRecent.textContent = (rclone.recent_transfers || []).length;
  if (countFailed) countFailed.textContent = (rclone.failed_transfers || []).length;

  // 7. Render Transfers Table for Current View
  renderTransfersTable(rclone);
}

function updateSparkline(currentBps) {
  speedHistory.push(currentBps);
  if (speedHistory.length > SPARKLINE_POINTS) {
    speedHistory.shift();
  }

  const lineEl = document.getElementById('sparkline-line');
  const areaEl = document.getElementById('sparkline-area');
  if (!lineEl || !areaEl) return;

  const maxBps = Math.max(1048576, ...speedHistory); // Minimum 1 MB/s scale ceiling
  const width = 120;
  const height = 40;
  const points = [];

  for (let i = 0; i < speedHistory.length; i++) {
    const x = (i / (SPARKLINE_POINTS - 1)) * width;
    const norm = Math.min(1, Math.max(0, speedHistory[i] / maxBps));
    const y = height - (norm * (height - 6)) - 2;
    points.push({ x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) });
  }

  if (points.length === 0) return;

  const lineD = points.map((p, idx) => `${idx === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
  const areaD = `${lineD} L ${width} ${height} L 0 ${height} Z`;

  lineEl.setAttribute('d', lineD);
  areaEl.setAttribute('d', areaD);
}

function renderFilePathNode(container, fullPath) {
  if (!container) return;
  container.replaceChildren();

  // Clean redundant internal prefix
  const clean = (fullPath || '').replace(/^library\/library\//, '').replace(/^library\//, '');
  const lastSlash = clean.lastIndexOf('/');

  const dir = lastSlash >= 0 ? clean.substring(0, lastSlash + 1) : '';
  const file = lastSlash >= 0 ? clean.substring(lastSlash + 1) : clean;

  const iconInfo = getMediaIcon(file);

  const iconSpan = document.createElement('span');
  iconSpan.className = `media-type-icon ${iconInfo.iconClass}`;
  iconSpan.innerHTML = iconInfo.svg;

  const pathWrap = document.createElement('span');
  pathWrap.className = 'path-wrap';

  if (dir) {
    const dirSpan = document.createElement('span');
    dirSpan.className = 'path-dir';
    dirSpan.textContent = dir;
    pathWrap.appendChild(dirSpan);
  }

  const fileSpan = document.createElement('span');
  fileSpan.className = 'path-filename';
  fileSpan.textContent = file;
  pathWrap.appendChild(fileSpan);

  container.appendChild(iconSpan);
  container.appendChild(pathWrap);
}

export function renderTransfersTable(rclone) {
  const tbody = document.getElementById('jobs-table-body');
  const emptyRow = document.getElementById('jobs-empty-row');
  const emptyMsg = document.getElementById('jobs-empty-msg');
  if (!tbody) return;

  if (currentView === 'active') {
    const jobs = rclone.jobs || [];
    if (jobs.length === 0) {
      if (emptyRow) emptyRow.classList.remove('hidden');
      const recentCount = (rclone.recent_transfers || []).length;
      if (emptyMsg) {
        if (recentCount > 0) {
          emptyMsg.innerHTML = `No active uploads right now. Mount cache is quiescent.<br><span style="font-size:12px; color:var(--text-muted);">See <a href="#" data-action="toggle-transfers-view" data-view="recent" style="color:var(--accent);">Recent (${recentCount})</a> for recently completed files.</span>`;
        } else {
          emptyMsg.textContent = 'No active uploads right now. Mount cache is quiescent.';
        }
      }
      reconcileList(tbody, [], 'tpl-job-row', j => j.name, () => {});
      return;
    }

    if (emptyRow) emptyRow.classList.add('hidden');
    reconcileList(tbody, jobs, 'tpl-job-row', j => j.name, (el, j) => {
      const cell = getBoundElement(el, 'file-cell');
      renderFilePathNode(cell, j.name);

      const pct = j.percentage || 0;
      const isFinalizing = pct >= 100;
      const progressLabel = isFinalizing ? 'Finalizing / Verifying...' : `${pct}%`;
      const fillClass = isFinalizing ? 'progress-fill finalizing' : (pct > 0 ? 'progress-fill green shimmer' : 'progress-fill green');
      const etaLabel = isFinalizing ? 'Commit' : (j.eta ? j.eta + 's' : '-');

      bindText(el, 'progress-label', progressLabel);
      bindStyle(el, 'progress-label', 'color', isFinalizing ? 'var(--amber)' : 'var(--heading)');
      bindText(el, 'bytes-label', `${j.bytes || '0 B'} / ${j.size || '0 B'}`);
      bindStyle(el, 'progress-bar', 'width', `${pct}%`);
      const barEl = getBoundElement(el, 'progress-bar');
      if (barEl) barEl.className = fillClass;

      bindText(el, 'speed', isFinalizing ? '-' : (j.speed || '0 B/s'));
      bindText(el, 'eta', etaLabel);
    });

  } else if (currentView === 'recent') {
    const recent = rclone.recent_transfers || [];
    if (recent.length === 0) {
      if (emptyRow) emptyRow.classList.remove('hidden');
      if (emptyMsg) emptyMsg.textContent = 'No completed uploads recorded in this session yet.';
      reconcileList(tbody, [], 'tpl-recent-row', r => r.name, () => {});
      return;
    }

    if (emptyRow) emptyRow.classList.add('hidden');
    reconcileList(tbody, recent, 'tpl-recent-row', r => `${r.name}_${r.completed_at}`, (el, r) => {
      const cell = getBoundElement(el, 'file-cell');
      renderFilePathNode(cell, r.name);

      const badge = getBoundElement(el, 'status-badge');
      if (badge) {
        badge.className = 'badge badge-green';
        badge.textContent = 'Committed';
      }

      bindText(el, 'size', r.size || '0 B');
      bindText(el, 'time', formatIsoRelativeTime(r.completed_at));
    });

  } else if (currentView === 'failed') {
    const failed = rclone.failed_transfers || [];
    if (failed.length === 0) {
      if (emptyRow) emptyRow.classList.remove('hidden');
      if (emptyMsg) emptyMsg.textContent = 'Zero failed transfers! System is operating cleanly.';
      reconcileList(tbody, [], 'tpl-recent-row', f => f.name, () => {});
      return;
    }

    if (emptyRow) emptyRow.classList.add('hidden');
    reconcileList(tbody, failed, 'tpl-recent-row', f => `${f.name}_${f.completed_at}`, (el, f) => {
      const cell = getBoundElement(el, 'file-cell');
      renderFilePathNode(cell, f.name);

      const badge = getBoundElement(el, 'status-badge');
      if (badge) {
        badge.className = 'badge badge-red';
        badge.textContent = f.error ? `Failed: ${f.error}` : 'Failed';
        badge.title = f.error || 'Transfer failed';
      }

      bindText(el, 'size', f.size || '0 B');
      bindText(el, 'time', formatIsoRelativeTime(f.completed_at));
    });
  }
}
