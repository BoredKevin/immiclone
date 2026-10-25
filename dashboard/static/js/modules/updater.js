/* ==========================================================================
   Updater & SemVer Controller
   Manages version indicators, update checks, and update modal
   ========================================================================== */

import * as api from './api.js';
import { formatRelativeTime, escapeHtml } from './formatters.js';

let latestVersion = null;
let latestUpdates = null;

export function getLatestVersion() {
  return latestVersion;
}

export function getLatestUpdates() {
  return latestUpdates;
}

export function updateVersionAndUpdates(versionData, updatesData) {
  if (versionData) latestVersion = versionData;
  if (updatesData) latestUpdates = updatesData;

  // 1. Update Brand Subtitle Version
  const brandVer = document.getElementById('brand-version');
  const dot = document.getElementById('header-version-dot');
  const txt = document.getElementById('header-version-text');

  const vTag = latestVersion ? latestVersion.version_tag || `v${latestVersion.version}` : 'v1.2.0';

  if (brandVer) {
    if (latestUpdates && latestUpdates.update_available) {
      brandVer.textContent = `${vTag} (Update available)`;
      brandVer.classList.add('has-update');
      brandVer.title = `Update available: ${latestUpdates.latest_commit}. Click to review.`;
    } else {
      brandVer.textContent = vTag;
      brandVer.classList.remove('has-update');
      brandVer.title = 'Up to date. Click to review version & commits.';
    }
  }

  if (latestUpdates && latestUpdates.update_available) {
    if (dot) dot.className = 'status-dot dot-amber dot-pulse';
    if (txt) txt.textContent = `Update (${latestUpdates.latest_commit})`;
  } else {
    if (dot) dot.className = 'status-dot dot-green';
    if (txt) txt.textContent = vTag;
  }

  // 2. Update Modal Dialog Elements if present
  renderUpdatesModalContent();
}

export function renderUpdatesModalContent() {
  const modal = document.getElementById('modal-updates');
  if (!modal) return;

  const ver = latestVersion || { version: '1.0.0', version_tag: 'v1.0.0', git: { commit_short: '6375510', branch: 'main' } };
  const upd = latestUpdates || { status: 'up_to_date', update_available: false, message: 'Up to date with main.' };

  const elCurVer = document.getElementById('update-cur-version');
  const elCurCommit = document.getElementById('update-cur-commit');
  const elBranch = document.getElementById('update-cur-branch');
  const elStatusDot = document.getElementById('update-status-dot');
  const elStatusText = document.getElementById('update-status-text');
  const elMsg = document.getElementById('update-status-msg');
  const elDetailsBox = document.getElementById('update-details-box');
  const elCommitMsg = document.getElementById('update-commit-msg');
  const elCommitMeta = document.getElementById('update-commit-meta');
  const elLastChecked = document.getElementById('update-last-checked');

  if (elCurVer) elCurVer.textContent = ver.version_tag || `v${ver.version}`;
  if (elCurCommit) elCurCommit.textContent = ver.git?.commit_short || '-';
  if (elBranch) elBranch.textContent = ver.git?.branch || 'main';

  if (upd.update_available) {
    if (elStatusDot) elStatusDot.className = 'status-dot dot-amber dot-pulse';
    if (elStatusText) elStatusText.textContent = 'Update Available';
    if (elMsg) elMsg.textContent = upd.message || 'A newer version is available on GitHub.';

    if (elDetailsBox) elDetailsBox.classList.remove('hidden');
    if (upd.latest_commit_details) {
      const d = upd.latest_commit_details;
      if (elCommitMsg) elCommitMsg.textContent = d.message || '-';
      if (elCommitMeta) {
        elCommitMeta.innerHTML = `Commit: <code class="mono">${escapeHtml(d.sha_short)}</code> • Author: <strong>${escapeHtml(d.author)}</strong> • ${escapeHtml(d.date ? d.date.split('T')[0] : '')}`;
      }
    }
  } else {
    if (elStatusDot) elStatusDot.className = 'status-dot dot-green';
    if (elStatusText) elStatusText.textContent = upd.status === 'rate_limited' ? 'Rate Limited' : 'Up to Date';
    if (elMsg) elMsg.textContent = upd.message || 'System is running the latest version.';
    if (elDetailsBox) elDetailsBox.classList.add('hidden');
  }

  if (elLastChecked && upd.last_checked) {
    const elapsed = Math.max(0, Math.floor(Date.now() / 1000 - upd.last_checked));
    elLastChecked.textContent = formatRelativeTime(elapsed);
  }
}

export async function openUpdatesModal() {
  const modal = document.getElementById('modal-updates');
  if (modal) modal.style.display = 'flex';

  if (!latestVersion) {
    try {
      latestVersion = await api.fetchVersion();
    } catch (e) {
      console.warn('[Updater] Failed to fetch version info:', e);
    }
  }

  if (!latestUpdates) {
    try {
      latestUpdates = await api.fetchUpdates();
    } catch (e) {
      console.warn('[Updater] Failed to fetch update info:', e);
    }
  }

  renderUpdatesModalContent();
}

export async function triggerUpdateCheckAction(btnEl) {
  let origText = '';
  if (btnEl) {
    origText = btnEl.innerHTML;
    btnEl.innerHTML = '<span class="status-dot dot-pulse dot-amber"></span> Checking...';
    btnEl.disabled = true;
  }

  try {
    const freshUpdates = await api.triggerUpdateCheck();
    latestUpdates = freshUpdates;
    renderUpdatesModalContent();
    updateVersionAndUpdates(latestVersion, latestUpdates);
  } catch (err) {
    alert('Failed to check for updates: ' + err);
  } finally {
    if (btnEl) {
      btnEl.innerHTML = origText;
      btnEl.disabled = false;
    }
  }
}
