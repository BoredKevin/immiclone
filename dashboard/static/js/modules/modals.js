/* ==========================================================================
   Modals Controller
   Manages dialogs, forms, and settings
   ========================================================================== */

import * as api from './api.js';
import { regenerateWorkerCmd } from './duplication.js';
import { escapeHtml } from './formatters.js';

export function openModal(name) {
  const modal = document.getElementById(`modal-${name}`);
  if (modal) modal.style.display = 'flex';
}

export function closeModal(name) {
  const modal = document.getElementById(`modal-${name}`);
  if (modal) modal.style.display = 'none';
}

// ==========================================================================
// Tailscale Modal
// ==========================================================================
export async function openTailscaleModal() {
  try {
    const cfg = await api.fetchTailscaleConfig();
    const modeEl = document.getElementById('ts-mode');
    const authKeyEl = document.getElementById('ts-auth-key');
    const tailnetEl = document.getElementById('ts-tailnet');
    const apiKeyEl = document.getElementById('ts-api-key');
    const autoInjEl = document.getElementById('ts-auto-inject');
    const ephEl = document.getElementById('ts-ephemeral');

    if (modeEl) modeEl.value = cfg.mode || 'auth_key';
    if (authKeyEl) {
      authKeyEl.value = '';
      authKeyEl.placeholder = cfg.masked_key || 'tskey-auth-...';
    }
    if (tailnetEl) tailnetEl.value = cfg.tailnet || '';
    if (apiKeyEl) {
      apiKeyEl.value = '';
      apiKeyEl.placeholder = cfg.masked_api || 'tskey-api-...';
    }
    if (autoInjEl) autoInjEl.checked = cfg.auto_inject !== false;
    if (ephEl) ephEl.checked = cfg.ephemeral !== false;

    toggleTsMode();
    openModal('tailscale');
  } catch (err) {
    console.error('[Modals] Failed to load Tailscale config:', err);
  }
}

export function toggleTsMode() {
  const mode = document.getElementById('ts-mode')?.value || 'auth_key';
  const fAuth = document.getElementById('ts-fields-auth');
  const fApi = document.getElementById('ts-fields-api');
  const fOauth = document.getElementById('ts-fields-oauth');

  if (fAuth) fAuth.style.display = mode === 'auth_key' ? 'block' : 'none';
  if (fApi) fApi.style.display = mode === 'api' ? 'block' : 'none';
  if (fOauth) fOauth.style.display = mode === 'oauth' ? 'block' : 'none';
}

export async function saveTailscaleConfig() {
  const mode = document.getElementById('ts-mode')?.value || 'auth_key';
  const payload = {
    mode: mode,
    auth_key: document.getElementById('ts-auth-key')?.value.trim() || '',
    tailnet: document.getElementById('ts-tailnet')?.value.trim() || '',
    api_key: document.getElementById('ts-api-key')?.value.trim() || '',
    oauth_client_id: document.getElementById('ts-oauth-id')?.value.trim() || '',
    oauth_client_secret: document.getElementById('ts-oauth-secret')?.value.trim() || '',
    auto_inject: document.getElementById('ts-auto-inject')?.checked ?? true,
    ephemeral: document.getElementById('ts-ephemeral')?.checked ?? true
  };

  try {
    await api.saveTailscaleConfig(payload);
    closeModal('tailscale');
    regenerateWorkerCmd();
  } catch (err) {
    alert('Failed to save Tailscale settings: ' + err);
  }
}

export async function deleteTailscaleKey() {
  if (!confirm('Are you sure you want to clear saved Tailscale credentials?')) return;
  try {
    await api.deleteTailscaleKey();
    closeModal('tailscale');
    regenerateWorkerCmd();
  } catch (err) {
    alert('Error clearing Tailscale key: ' + err);
  }
}

export async function testTailscaleKey() {
  try {
    const data = await api.testTailscaleKey();
    alert(`[Tailscale Test Result]\nStatus: ${data.status}\nMessage: ${data.message}`);
  } catch (err) {
    alert('Error testing Tailscale key: ' + err);
  }
}

// ==========================================================================
// Settings Modal
// ==========================================================================
export async function openSettingsModal() {
  try {
    const data = await api.fetchSettings();
    const st = data.storage || {};

    const elRemote = document.getElementById('settings-primary-remote');
    const elVfs = document.getElementById('settings-vfs-cache-max');
    const elRcUrl = document.getElementById('settings-rc-url');
    const elMount = document.getElementById('settings-mount-base');
    const elCache = document.getElementById('settings-cache-base');

    if (elRemote) elRemote.value = st.primary_remote || '';
    if (elVfs) elVfs.value = st.vfs_cache_max_gb || 10.0;
    if (elRcUrl) elRcUrl.value = st.rclone_rc_url || 'http://localhost:5572';
    if (elMount) elMount.value = st.mount_base || '/mnt/immiclone';
    if (elCache) elCache.value = st.cache_base || '/var/cache/immiclone/vfs';

    openModal('settings');
  } catch (err) {
    console.error('[Modals] Failed to load settings:', err);
  }
}

export async function saveSettingsConfig() {
  const elRemote = document.getElementById('settings-primary-remote');
  const elVfs = document.getElementById('settings-vfs-cache-max');
  const elRcUrl = document.getElementById('settings-rc-url');
  const elMount = document.getElementById('settings-mount-base');
  const elCache = document.getElementById('settings-cache-base');

  const payload = {
    storage: {
      primary_remote: elRemote ? elRemote.value.trim() : '',
      vfs_cache_max_gb: elVfs ? parseFloat(elVfs.value) || 10.0 : 10.0,
      rclone_rc_url: elRcUrl ? elRcUrl.value.trim() : 'http://localhost:5572',
      mount_base: elMount ? elMount.value.trim() : '/mnt/immiclone',
      cache_base: elCache ? elCache.value.trim() : '/var/cache/immiclone/vfs'
    }
  };

  try {
    await api.saveSettings(payload);
    closeModal('settings');
    regenerateWorkerCmd();
  } catch (err) {
    alert('Failed to save settings: ' + err);
  }
}

// ==========================================================================
// Transactions Modals
// ==========================================================================
export async function loadRemotes() {
  try {
    const data = await api.fetchRemotes();
    const destDl = document.getElementById('dest-remotes-list');
    const srcDl = document.getElementById('source-remotes-list');
    if (data.remotes) {
      const opts = data.remotes.map(r => `<option value="${r}"></option>`).join('');
      if (destDl) destDl.innerHTML = opts;
      if (srcDl) srcDl.innerHTML = opts;
    }
  } catch (e) {
    console.error('[Modals] Failed to load remotes:', e);
  }
}

export function applyTxPreset(presetKey) {
  const titleEl = document.getElementById('tx-title');
  const srcEl = document.getElementById('tx-source');
  const dstEl = document.getElementById('tx-dest');
  const modeEl = document.getElementById('tx-mode');
  const prioEl = document.getElementById('tx-priority');
  const flagsEl = document.getElementById('tx-flags');
  const notesEl = document.getElementById('tx-notes');

  if (presetKey === 'gdrive-mirror') {
    if (titleEl) titleEl.value = 'Google Drive Cloud Mirror';
    if (srcEl) srcEl.value = 'bkc:media';
    if (dstEl) dstEl.value = 'gdrive-backup:archive';
    if (modeEl) modeEl.value = 'sync';
    if (prioEl) prioEl.value = 'high';
    if (flagsEl) flagsEl.value = '--fast-list --transfers=8 --checkers=16 --drive-chunk-size=64M';
    if (notesEl) notesEl.value = 'Direct gigabit cloud-to-cloud replication';
  } else if (presetKey === 'local-ssd-backup') {
    if (titleEl) titleEl.value = 'Local SSD Backup';
    if (srcEl) srcEl.value = 'bkc:media';
    if (dstEl) dstEl.value = '/mnt/ssd/immich-backup';
    if (modeEl) modeEl.value = 'copy';
    if (prioEl) prioEl.value = 'normal';
    if (flagsEl) flagsEl.value = '--size-only --transfers=4 --checkers=8';
    if (notesEl) notesEl.value = 'Local fast NVMe replication backup';
  } else if (presetKey === 'bidirectional-verify') {
    if (titleEl) titleEl.value = 'Integrity Check Audit';
    if (srcEl) srcEl.value = 'bkc:media';
    if (dstEl) dstEl.value = '/mnt/ssd/immich-backup';
    if (modeEl) modeEl.value = 'check';
    if (prioEl) prioEl.value = 'low';
    if (flagsEl) flagsEl.value = '--one-way --checkers=16';
    if (notesEl) notesEl.value = 'SHA-256 hash checksum integrity check';
  }
}

export function openNewTxModal() {
  const titleEl = document.getElementById('tx-title');
  const srcEl = document.getElementById('tx-source');
  const dstEl = document.getElementById('tx-dest');
  const flagsEl = document.getElementById('tx-flags');
  const notesEl = document.getElementById('tx-notes');
  if (titleEl) titleEl.value = '';
  if (srcEl) srcEl.value = '';
  if (dstEl) dstEl.value = '';
  if (flagsEl) flagsEl.value = '--size-only --drive-chunk-size=64M --drive-upload-cutoff=64M --buffer-size=32M --transfers=4 --checkers=8 --tpslimit=10 --drive-pacer-min-sleep=10ms';
  if (notesEl) notesEl.value = '';
  openModal('new-tx');
  loadRemotes().catch(() => {});
}

export async function submitCreateTx() {
  const src = document.getElementById('tx-source')?.value.trim() || '';
  const dst = document.getElementById('tx-dest')?.value.trim() || '';
  if (!src) {
    alert('Please enter a source remote or path (e.g. boredkevinmedia:crypt).');
    return;
  }
  if (!dst) {
    alert('Please enter a destination remote or path (e.g. 1337quota:crypt).');
    return;
  }
  const flagsInput = document.getElementById('tx-flags')?.value.trim() || '';
  const defaultFlags = [
    '--size-only',
    '--drive-chunk-size=64M',
    '--drive-upload-cutoff=64M',
    '--buffer-size=32M',
    '--transfers=4',
    '--checkers=8',
    '--tpslimit=10',
    '--drive-pacer-min-sleep=10ms'
  ];
  const payload = {
    title: document.getElementById('tx-title')?.value.trim() || `${src} -> ${dst}`,
    source: src,
    dest: dst,
    mode: document.getElementById('tx-mode')?.value || 'copy',
    priority: document.getElementById('tx-priority')?.value || 'normal',
    rclone_flags: flagsInput ? flagsInput.split(/\s+/) : defaultFlags,
    notes: document.getElementById('tx-notes')?.value.trim() || ''
  };

  try {
    const res = await api.createTx(payload);
    if (res && res.validation && res.validation.warning) {
      alert(`[Notice] ${res.validation.warning}`);
    }
    closeModal('new-tx');
  } catch (err) {
    alert('Error creating transaction: ' + err);
  }
}

export function openEditTxModal(txId, transactions) {
  const tx = (transactions || []).find(t => t.tx_id === txId);
  if (!tx) return;

  const idEl = document.getElementById('edit-tx-id');
  const titleEl = document.getElementById('edit-tx-title');
  const srcEl = document.getElementById('edit-tx-source');
  const dstEl = document.getElementById('edit-tx-dest');
  const modeEl = document.getElementById('edit-tx-mode');
  const priorityEl = document.getElementById('edit-tx-priority');
  const flagsEl = document.getElementById('edit-tx-flags');
  const notesEl = document.getElementById('edit-tx-notes');

  if (idEl) idEl.value = tx.tx_id;
  if (titleEl) titleEl.value = tx.title || '';
  if (srcEl) srcEl.value = tx.source || '';
  if (dstEl) dstEl.value = tx.dest || '';
  if (modeEl) modeEl.value = tx.mode || 'copy';
  if (priorityEl) priorityEl.value = tx.priority || 'normal';
  if (flagsEl) flagsEl.value = Array.isArray(tx.rclone_flags) ? tx.rclone_flags.join(' ') : (tx.rclone_flags || '');
  if (notesEl) notesEl.value = tx.notes || '';

  openModal('edit-tx');
}

export async function submitEditTx() {
  const flagsInput = document.getElementById('edit-tx-flags')?.value.trim() || '';
  const payload = {
    tx_id: document.getElementById('edit-tx-id')?.value || '',
    title: document.getElementById('edit-tx-title')?.value.trim() || '',
    source: document.getElementById('edit-tx-source')?.value.trim() || '',
    dest: document.getElementById('edit-tx-dest')?.value.trim() || '',
    mode: document.getElementById('edit-tx-mode')?.value || 'copy',
    priority: document.getElementById('edit-tx-priority')?.value || 'normal',
    rclone_flags: flagsInput ? flagsInput.split(/\s+/) : ['--size-only'],
    notes: document.getElementById('edit-tx-notes')?.value.trim() || ''
  };

  try {
    await api.updateTx(payload);
    closeModal('edit-tx');
  } catch (err) {
    alert('Error updating transaction: ' + err);
  }
}

// ==========================================================================
// Worker Modals
// ==========================================================================
export function openNewWorkerModal() {
  const titleEl = document.getElementById('worker-modal-title');
  const idEl = document.getElementById('worker-modal-id');
  const nameEl = document.getElementById('worker-name');
  const notesEl = document.getElementById('worker-notes');

  if (titleEl) titleEl.textContent = 'Pre-Register Worker';
  if (idEl) idEl.value = '';
  if (nameEl) nameEl.value = 'Cloud Shell Worker';
  if (notesEl) notesEl.value = 'Google Cloud Shell';

  openModal('worker');
}

export function openEditWorkerModal(wid, workers) {
  const w = (workers || []).find(x => x.id === wid);
  if (!w) return;

  const titleEl = document.getElementById('worker-modal-title');
  const idEl = document.getElementById('worker-modal-id');
  const nameEl = document.getElementById('worker-name');
  const notesEl = document.getElementById('worker-notes');

  if (titleEl) titleEl.textContent = `Edit Worker: ${wid}`;
  if (idEl) idEl.value = wid;
  if (nameEl) nameEl.value = w.name || '';
  if (notesEl) notesEl.value = w.notes || '';

  openModal('worker');
}

export async function submitWorkerModal() {
  const wid = document.getElementById('worker-modal-id')?.value;
  const name = document.getElementById('worker-name')?.value.trim() || '';
  const notes = document.getElementById('worker-notes')?.value.trim() || '';

  try {
    if (wid) {
      await api.updateWorker({ worker_id: wid, name, notes });
    } else {
      await api.createWorker({ name, notes });
    }
    closeModal('worker');
    regenerateWorkerCmd();
  } catch (err) {
    alert('Error saving worker: ' + err);
  }
}
