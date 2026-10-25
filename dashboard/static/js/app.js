/* ==========================================================================
   Immiclone Frontend Application & Telemetry Engine
   Modular ES Architecture with Declarative Templates & Root Event Delegation
   ========================================================================== */

import { initEventDelegation, registerAction, registerChange, registerInput } from './modules/events.js';
import { startSSE, getLatestPayload, setPollingInterval } from './modules/sse.js';
import { setTransfersView, toggleMountPause } from './modules/mount.js';
import {
  setTxFilter,
  setWorkerFilter,
  selectRunnerPreset,
  initWorkerCmdBar,
  regenerateWorkerCmd,
  copyWorkerCmd
} from './modules/duplication.js';
import {
  loadMedia,
  sortMediaTable,
  changePage,
  setMediaFilter,
  onSearchInput
} from './modules/media.js';
import {
  openModal,
  closeModal,
  openTailscaleModal,
  toggleTsMode,
  saveTailscaleConfig,
  deleteTailscaleKey,
  testTailscaleKey,
  openSettingsModal,
  saveSettingsConfig,
  openNewTxModal,
  applyTxPreset,
  submitCreateTx,
  openEditTxModal,
  submitEditTx,
  openNewWorkerModal,
  openEditWorkerModal,
  submitWorkerModal
} from './modules/modals.js';
import { openUpdatesModal, triggerUpdateCheckAction } from './modules/updater.js';
import * as api from './modules/api.js';

// ==========================================================================
// Tab Switching
// ==========================================================================
export function switchNav(tab) {
  document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  const navBtn = document.getElementById(`tab-nav-${tab}`);
  const content = document.getElementById(`content-${tab}`);
  if (navBtn) navBtn.classList.add('active');
  if (content) content.classList.add('active');
  if (tab === 'media') loadMedia();
}

// ==========================================================================
// Action Registrations ([data-action])
// ==========================================================================

// Navigation
registerAction('switch-tab', (data) => switchNav(data.tab));

// Modals: Open & Close
registerAction('open-modal', (data) => {
  const target = data.target;
  if (target === 'tailscale') openTailscaleModal();
  else if (target === 'settings') openSettingsModal();
  else if (target === 'new-tx') openNewTxModal();
  else if (target === 'new-worker') openNewWorkerModal();
  else if (target === 'updates') openUpdatesModal();
  else openModal(target);
});
registerAction('close-modal', (data) => closeModal(data.target));

// Updates Modal Actions
registerAction('check-updates', (data, target) => triggerUpdateCheckAction(target));

// Tailscale Modal Actions
registerAction('save-tailscale', () => saveTailscaleConfig());
registerAction('delete-tailscale', () => deleteTailscaleKey());
registerAction('test-tailscale', () => testTailscaleKey());

// Settings Modal Actions
registerAction('save-settings', () => saveSettingsConfig());

// Transaction Creation & Editing
registerAction('submit-create-tx', () => submitCreateTx());
registerAction('submit-edit-tx', () => submitEditTx());

// Worker Modal Actions
registerAction('submit-worker-modal', () => submitWorkerModal());

// Ephemeral Worker Launcher & Runner Presets
registerAction('new-session', () => regenerateWorkerCmd(true));
registerAction('copy-worker-cmd', (data, target) => copyWorkerCmd(target));
registerAction('select-runner-preset', (data) => selectRunnerPreset(data.preset));
registerAction('open-cloud-shell', () => {
  window.open('https://shell.cloud.google.com/?show=terminal', '_blank', 'noopener,noreferrer');
});

// Transaction Presets
registerAction('apply-tx-preset', (data) => applyTxPreset(data.preset));
registerAction('guided-create-tx', (data) => {
  openNewTxModal();
  applyTxPreset(data.preset);
});

// Duplication Transactions List Actions
registerAction('filter-tx', (data) => setTxFilter(data.filter));

registerAction('clear-completed-tx', async () => {
  if (!confirm('Clear all finished and cancelled duplication transactions?')) return;
  try {
    await api.clearCompletedTx();
  } catch (err) {
    alert('Error clearing transactions: ' + err);
  }
});

registerAction('pause-tx', async (data) => {
  try {
    await api.pauseTx(data.id);
  } catch (err) {
    alert('Error pausing transaction: ' + err);
  }
});

registerAction('cancel-tx', async (data) => {
  if (!confirm(`Are you sure you want to cancel transaction ${data.id}?`)) return;
  try {
    await api.cancelTx(data.id);
  } catch (err) {
    alert('Error cancelling transaction: ' + err);
  }
});

registerAction('assign-tx', async (data, target) => {
  const card = target.closest('[data-key]');
  const sel = card ? card.querySelector('[data-bind="assign-select"]') : null;
  const workerId = sel ? sel.value : null;
  if (!workerId) {
    alert('Please select an active worker to assign.');
    return;
  }
  try {
    await api.assignTx(data.id, workerId);
  } catch (err) {
    alert('Error assigning transaction: ' + err);
  }
});

registerAction('edit-tx', (data) => {
  const payload = getLatestPayload();
  openEditTxModal(data.id, payload.transactions || []);
});

registerAction('reset-tx', async (data) => {
  if (!confirm(`Reset progress of transaction ${data.id} to 0?`)) return;
  try {
    await api.resetTxProgress(data.id);
  } catch (err) {
    alert('Error resetting transaction: ' + err);
  }
});

registerAction('delete-tx', async (data) => {
  if (!confirm(`Permanently delete transaction ${data.id}?`)) return;
  try {
    await api.deleteTx(data.id);
  } catch (err) {
    alert('Error deleting transaction: ' + err);
  }
});

registerAction('requeue-tx', async (data) => {
  try {
    await api.requeueTx(data.id);
  } catch (err) {
    alert('Error requeuing transaction: ' + err);
  }
});

// Workers List Actions
registerAction('filter-worker', (data) => setWorkerFilter(data.filter));

registerAction('prune-offline-workers', async () => {
  if (!confirm('Remove all offline workers from registry?')) return;
  try {
    await api.pruneOfflineWorkers();
  } catch (err) {
    alert('Error pruning offline workers: ' + err);
  }
});

registerAction('edit-worker', (data) => {
  const payload = getLatestPayload();
  openEditWorkerModal(data.id, payload.workers || []);
});

registerAction('stop-worker', async (data) => {
  if (!confirm(`Disconnect worker ${data.id}?`)) return;
  try {
    await api.disconnectWorker(data.id);
  } catch (err) {
    alert('Error disconnecting worker: ' + err);
  }
});

registerAction('refresh-worker-token', async (data) => {
  if (!confirm(`Rotate and refresh authentication token for worker ${data.id}?`)) return;
  try {
    const res = await api.refreshWorkerToken(data.id);
    alert(`Authentication token refreshed for worker ${data.id}.\nNew Token: ${res.token}`);
  } catch (err) {
    alert('Error refreshing worker token: ' + err);
  }
});

registerAction('delete-worker', async (data) => {
  if (!confirm(`Remove worker ${data.id} from registry?`)) return;
  try {
    await api.deleteWorker(data.id);
  } catch (err) {
    alert('Error removing worker: ' + err);
  }
});

// Media & Cache Catalog Actions
registerAction('filter-media', (data) => setMediaFilter(data.filter));
registerAction('sort-media', (data) => sortMediaTable(data.col));
registerAction('change-page', (data) => changePage(parseInt(data.delta, 10) || 0));

// Transfers Table & Mount Actions
registerAction('toggle-transfers-view', (data) => setTransfersView(data.view));
registerAction('toggle-mount-pause', () => toggleMountPause());

// ==========================================================================
// Change Registrations ([data-change])
// ==========================================================================
registerChange('toggle-auto-ts', () => {
  if (sessionStorage.getItem('immiclone_worker_cmd')) {
    regenerateWorkerCmd(false);
  }
});
registerChange('toggle-ts-mode', () => toggleTsMode());

// ==========================================================================
// Input Registrations ([data-input])
// ==========================================================================
registerInput('search-media', (val) => onSearchInput(val));

// ==========================================================================
// Application Bootstrap
// ==========================================================================
function initApp() {
  initEventDelegation();
  startSSE();
  initWorkerCmdBar();

  const pollSel = document.getElementById('poll-interval-select');
  if (pollSel) {
    pollSel.addEventListener('change', (e) => {
      const ms = parseInt(e.target.value, 10);
      setPollingInterval(ms);
    });
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
