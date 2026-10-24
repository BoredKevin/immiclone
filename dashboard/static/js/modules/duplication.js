/* ==========================================================================
   Duplication Manager Controller (Tab 1)
   Implements Rule 1: Action buttons directly in <template>, toggled via .hidden
   ========================================================================== */

import { reconcileList, bindText, bindStyle, bindClass, bindHidden, getBoundElement } from './dom.js';
import { formatRelativeTime, populateFlagPills, formatCommandHtml, maskCommandSecret, escapeHtml } from './formatters.js';
import * as api from './api.js';

let currentTxFilter = 'all';
let currentWorkerFilter = 'all';
let latestTransactions = [];
let latestWorkers = [];
let fullWorkerCommand = '';

export function getFullWorkerCommand() {
  return fullWorkerCommand;
}

export function setTxFilter(filter) {
  currentTxFilter = filter;
  document.querySelectorAll('[data-action="filter-tx"]').forEach(el => {
    el.classList.toggle('active', el.dataset.filter === filter);
  });
  renderTransactions(latestTransactions, latestWorkers);
}

export function setWorkerFilter(filter) {
  currentWorkerFilter = filter;
  document.querySelectorAll('[data-action="filter-worker"]').forEach(el => {
    el.classList.toggle('active', el.dataset.filter === filter);
  });
  renderWorkers(latestWorkers);
}

export function updateDuplicationData(transactions, workers) {
  latestTransactions = transactions || [];
  latestWorkers = workers || [];

  const navCount = document.getElementById('nav-tx-count');
  if (navCount) navCount.textContent = latestTransactions.length;

  renderTransactions(latestTransactions, latestWorkers);
  renderWorkers(latestWorkers);
}

export function renderTransactions(txList, workers) {
  const container = document.getElementById('transactions-container');
  if (!container) return;

  const runningCount = txList.filter(t => t.status === 'RUNNING').length;
  const queuedCount = txList.filter(t => t.status === 'QUEUED').length;
  const pausedCount = txList.filter(t => ['PAUSED', 'INTERRUPTED'].includes(t.status)).length;
  const completedCount = txList.filter(t => ['COMPLETED', 'CANCELLED'].includes(t.status)).length;

  const countAll = document.getElementById('count-tx-all');
  const countRunning = document.getElementById('count-tx-running');
  const countQueued = document.getElementById('count-tx-queued');
  const countPaused = document.getElementById('count-tx-paused');
  const countCompleted = document.getElementById('count-tx-completed');

  if (countAll) countAll.textContent = txList.length;
  if (countRunning) countRunning.textContent = runningCount;
  if (countQueued) countQueued.textContent = queuedCount;
  if (countPaused) countPaused.textContent = pausedCount;
  if (countCompleted) countCompleted.textContent = completedCount;

  let filtered = txList;
  if (currentTxFilter === 'running') filtered = txList.filter(t => t.status === 'RUNNING');
  else if (currentTxFilter === 'queued') filtered = txList.filter(t => t.status === 'QUEUED');
  else if (currentTxFilter === 'paused') filtered = txList.filter(t => ['PAUSED', 'INTERRUPTED'].includes(t.status));
  else if (currentTxFilter === 'completed') filtered = txList.filter(t => ['COMPLETED', 'CANCELLED'].includes(t.status));

  const emptyState = document.getElementById('tx-empty-state');
  if (emptyState) {
    emptyState.classList.toggle('hidden', filtered.length > 0);
    if (filtered.length === 0) {
      emptyState.textContent = `No duplication transactions matching filter '${currentTxFilter}'.`;
    }
  }

  const standbyWorkers = workers.filter(w => w.status === 'STANDBY');

  // Reconcile cards in-place using declarative <template id="tpl-tx-card">
  reconcileList(container, filtered, 'tpl-tx-card', t => t.tx_id, (el, tx, isNew) => {
    const isRunning = tx.status === 'RUNNING';
    const isQueued = tx.status === 'QUEUED';
    const isInterrupted = tx.status === 'INTERRUPTED';
    const isPaused = tx.status === 'PAUSED';
    const isCompleted = tx.status === 'COMPLETED';
    const isCancelled = tx.status === 'CANCELLED';

    // Header & metadata
    bindText(el, 'title', tx.title || 'Duplication Transaction');
    bindText(el, 'route', `${tx.source} → ${tx.dest}`);
    bindText(el, 'mode', (tx.mode || 'copy').toUpperCase());
    bindText(el, 'tx-id', tx.tx_id);
    bindText(el, 'worker-name', tx.assigned_worker || 'None');

    // Status badge
    const badgeEl = getBoundElement(el, 'status-badge');
    if (badgeEl) {
      if (isRunning) {
        badgeEl.className = 'badge badge-running';
        badgeEl.innerHTML = `<span class="status-dot dot-green dot-pulse"></span> RUNNING (Lease #${tx.lease_id || 1})`;
      } else if (isQueued) {
        badgeEl.className = 'badge badge-queued';
        badgeEl.innerHTML = '<span class="status-dot dot-amber"></span> QUEUED';
      } else if (isInterrupted) {
        badgeEl.className = 'badge badge-interrupted';
        badgeEl.innerHTML = '<span class="status-dot dot-red"></span> INTERRUPTED';
      } else if (isPaused) {
        badgeEl.className = 'badge badge-paused';
        badgeEl.innerHTML = '<span class="status-dot dot-gray"></span> PAUSED';
      } else if (isCompleted) {
        badgeEl.className = 'badge badge-completed';
        badgeEl.innerHTML = '<span class="status-dot dot-purple"></span> COMPLETED';
      } else if (isCancelled) {
        badgeEl.className = 'badge badge-interrupted';
        badgeEl.innerHTML = '<span class="status-dot dot-red"></span> CANCELLED';
      }
    }

    // Flags micro-pills
    populateFlagPills(getBoundElement(el, 'flags-container'), tx.rclone_flags);

    // Notes
    const notesWrap = getBoundElement(el, 'notes-wrap');
    if (notesWrap) {
      if (tx.notes) {
        notesWrap.className = '';
        notesWrap.innerHTML = `<span class="tx-meta-sep">•</span> <span>Notes: ${escapeHtml(tx.notes)}</span>`;
      } else {
        notesWrap.className = 'hidden';
      }
    }

    // Telemetry readouts
    const pct = tx.percentage || 0;
    const speed = tx.speed_human || '0 B/s';
    const isSpeedActive = speed !== '0 B/s' && speed !== '0.0 B/s';
    const transferredGb = ((tx.bytes_transferred || 0) / (1024**3)).toFixed(2);
    const totalGb = ((tx.total_bytes || 0) / (1024**3)).toFixed(2);

    bindText(el, 'progress-text', `${pct}% (${transferredGb} GB / ${totalGb} GB)`);
    bindText(el, 'speed', speed);
    bindStyle(el, 'speed', 'color', isSpeedActive ? 'var(--green-light)' : 'var(--text-muted)');
    bindText(el, 'files', `${(tx.files_transferred || 0).toLocaleString()} copied (${(tx.files_checked || 0).toLocaleString()} checked)`);
    bindText(el, 'eta', tx.eta_sec ? tx.eta_sec + 's' : '-');

    // Progress bar
    bindStyle(el, 'progress-fill', 'width', `${pct}%`);
    let fillClass = 'green';
    if (isQueued || isPaused) fillClass = 'amber';
    else if (isInterrupted || isCancelled) fillClass = 'red';
    else if (isCompleted) fillClass = 'purple';
    if (isRunning) fillClass += ' running';
    const fillEl = getBoundElement(el, 'progress-fill');
    if (fillEl) fillEl.className = `progress-fill ${fillClass}`;

    bindText(el, 'current-file', tx.current_file || 'Idle');

    // Rule 1: Toggle action buttons directly in <template> via .hidden (Zero destruction)
    if (isRunning) {
      bindHidden(el, 'actions-running', false);
      bindHidden(el, 'actions-pending', true);
      bindHidden(el, 'actions-completed', true);
    } else if (isQueued || isInterrupted || isPaused) {
      bindHidden(el, 'actions-running', true);
      bindHidden(el, 'actions-pending', false);
      bindHidden(el, 'actions-completed', true);
      bindText(el, 'assign-btn-label', isQueued ? 'Start on Worker' : 'Resume on Worker');

      // Update worker <select> without resetting active focus or selection
      const sel = getBoundElement(el, 'assign-select');
      if (sel) {
        if (standbyWorkers.length > 0) {
          bindHidden(el, 'assign-group', false);
          bindHidden(el, 'no-workers-msg', true);

          // Update options only if workers changed to preserve selection
          const prevVal = sel.value;
          const optionsSig = standbyWorkers.map(w => w.id).join(',');
          if (sel.dataset.sig !== optionsSig) {
            sel.dataset.sig = optionsSig;
            sel.innerHTML = standbyWorkers.map(w =>
              `<option value="${w.id}">${escapeHtml(w.name || w.id)} (${escapeHtml(w.hostname)})</option>`
            ).join('');
            if (prevVal && standbyWorkers.some(w => w.id === prevVal)) {
              sel.value = prevVal;
            }
          }
        } else {
          bindHidden(el, 'assign-group', true);
          bindHidden(el, 'no-workers-msg', false);
        }
      }
    } else {
      // Completed or Cancelled
      bindHidden(el, 'actions-running', true);
      bindHidden(el, 'actions-pending', true);
      bindHidden(el, 'actions-completed', false);
    }
  });
}

export function renderWorkers(workers) {
  const tbody = document.getElementById('workers-table-body');
  if (!tbody) return;

  const activeCount = workers.filter(w => w.status !== 'OFFLINE').length;
  const offlineCount = workers.filter(w => w.status === 'OFFLINE').length;

  const countAll = document.getElementById('count-w-all');
  const countActive = document.getElementById('count-w-active');
  const countOffline = document.getElementById('count-w-offline');

  if (countAll) countAll.textContent = workers.length;
  if (countActive) countActive.textContent = activeCount;
  if (countOffline) countOffline.textContent = offlineCount;

  let filtered = workers;
  if (currentWorkerFilter === 'active') filtered = workers.filter(w => w.status !== 'OFFLINE');
  else if (currentWorkerFilter === 'offline') filtered = workers.filter(w => w.status === 'OFFLINE');

  const emptyRow = document.getElementById('workers-empty-row');
  if (emptyRow) {
    emptyRow.classList.toggle('hidden', filtered.length > 0);
  }

  // Reconcile worker rows in-place using declarative <template id="tpl-worker-row">
  reconcileList(tbody, filtered, 'tpl-worker-row', w => w.id, (el, w, isNew) => {
    const isRunning = w.status === 'RUNNING';
    const isOffline = w.status === 'OFFLINE';

    // Status dot & text
    const dot = getBoundElement(el, 'status-dot');
    if (dot) {
      if (isRunning) dot.className = 'status-dot dot-green dot-pulse';
      else if (isOffline) dot.className = 'status-dot dot-red';
      else dot.className = 'status-dot dot-amber';
    }
    bindText(el, 'status-text', isRunning ? 'Running' : (isOffline ? 'Offline' : 'Standby'));

    bindText(el, 'name', w.name || w.id);
    bindText(el, 'id', w.id);

    // Semver badge & matching indicator
    const wVer = w.version || '1.0.1';
    const verBadge = el.querySelector('[data-bind="version-badge"]');
    if (verBadge) {
      verBadge.textContent = wVer.startsWith('v') ? wVer : `v${wVer}`;
      if (w.version_match !== false) {
        verBadge.style.background = 'rgba(16, 185, 129, 0.15)';
        verBadge.style.color = '#34d399';
        verBadge.title = 'Worker semver matches server';
      } else {
        verBadge.style.background = 'rgba(239, 68, 68, 0.15)';
        verBadge.style.color = '#f87171';
        verBadge.title = `Worker semver (${wVer}) differs from server`;
      }
    }

    bindText(el, 'hostname', w.hostname || '-');
    bindText(el, 'current-tx', w.current_tx || '-');

    const relTime = formatRelativeTime(w.last_seen_sec);
    bindText(el, 'last-seen', isOffline ? `Offline (${relTime})` : `Active (${relTime})`);
    bindStyle(el, 'last-seen', 'color', isOffline ? 'var(--text-muted)' : 'var(--green-light)');
    bindText(el, 'notes', w.notes || '-');

    // Rule 1: Action button toggles directly inside <template>
    bindHidden(el, 'btn-stop-worker', !isRunning);
    bindHidden(el, 'btn-delete-worker', false);
  });
}

const STORAGE_KEY = 'immiclone_worker_cmd';

export function initWorkerCmdBar() {
  const saved = sessionStorage.getItem(STORAGE_KEY);
  const displayEl = document.getElementById('worker-cmd-display');
  if (saved) {
    fullWorkerCommand = saved;
    if (displayEl) {
      displayEl.innerHTML = formatCommandHtml(saved);
      displayEl.title = 'Hover over blurred keys to reveal. Click Copy Command to copy the full command.';
    }
  } else {
    // Show standby placeholder without generating a new session or minting an auth key
    if (displayEl) {
      displayEl.innerHTML = '<span style="color:var(--text-muted);">curl -sSL https://raw.githubusercontent.com/BoredKevin/immiclone/refs/heads/main/worker/worker-stable.sh | bash <em>(Click &ldquo;Copy Command&rdquo; or &ldquo;New Session&rdquo; to launch)</em></span>';
      displayEl.title = 'Click Copy Command or New Session to generate a runner session';
    }
  }
}

export async function regenerateWorkerCmd(forceFresh = false) {
  const chk = document.getElementById('chk-auto-ts');
  const includeTs = chk ? chk.checked : true;
  const displayEl = document.getElementById('worker-cmd-display');
  if (displayEl) {
    displayEl.innerHTML = '<span style="color:var(--text-dim);">Initializing runner session...</span>';
  }
  try {
    const data = await api.createWorkerSession(includeTs, forceFresh);
    fullWorkerCommand = data.one_liner || '';
    if (fullWorkerCommand) {
      sessionStorage.setItem(STORAGE_KEY, fullWorkerCommand);
    }
    if (displayEl) {
      displayEl.innerHTML = formatCommandHtml(fullWorkerCommand);
      displayEl.title = 'Hover over blurred keys to reveal. Click Copy Command to copy the full command.';
    }
    return fullWorkerCommand;
  } catch (e) {
    fullWorkerCommand = 'curl -sSL https://raw.githubusercontent.com/BoredKevin/immiclone/refs/heads/main/worker/worker-stable.sh | bash';
    if (displayEl) displayEl.innerHTML = formatCommandHtml(fullWorkerCommand);
    return fullWorkerCommand;
  }
}

export async function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      // Fall through to DOM fallback
    }
  }

  // Fallback for non-HTTPS or non-secure contexts (e.g. plain HTTP IP/Tailscale origin)
  try {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '0';
    textArea.style.left = '0';
    textArea.style.width = '2em';
    textArea.style.height = '2em';
    textArea.style.padding = '0';
    textArea.style.border = 'none';
    textArea.style.outline = 'none';
    textArea.style.boxShadow = 'none';
    textArea.style.background = 'transparent';
    textArea.style.opacity = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    return successful;
  } catch (err) {
    console.error('Fallback clipboard copy failed:', err);
    return false;
  }
}

export async function copyWorkerCmd(targetBtn) {
  let cmd = fullWorkerCommand;
  if (!cmd) {
    // Generate session on-demand if user copies before generating
    cmd = await regenerateWorkerCmd(false);
  }
  if (!cmd) {
    cmd = document.getElementById('worker-cmd-display')?.innerText || '';
  }
  if (!cmd) return;

  const ok = await copyToClipboard(cmd);
  if (ok) {
    if (targetBtn) {
      const orig = targetBtn.innerHTML;
      targetBtn.innerHTML = '✓ Copied!';
      setTimeout(() => { targetBtn.innerHTML = orig; }, 1800);
    }
  } else {
    alert('Could not copy command to clipboard.');
  }
}
