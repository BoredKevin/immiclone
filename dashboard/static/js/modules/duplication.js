/* ==========================================================================
   Duplication Manager Controller (Tab 1 & Stage 3 Workspace)
   Implements Rule 1: Action buttons directly in <template>, toggled via .hidden
   ========================================================================== */

import { reconcileList, bindText, bindStyle, bindClass, bindHidden, getBoundElement } from './dom.js';
import { formatRelativeTime, populateFlagPills, formatCommandHtml, maskCommandSecret, escapeHtml } from './formatters.js';
import * as api from './api.js';

let currentTxFilter = 'all';
let currentWorkerFilter = 'all';
let activeRunnerPreset = 'cloud-shell';
let latestTransactions = [];
let latestWorkers = [];
let fullWorkerCommand = '';

export function getFullWorkerCommand() {
  return generatePresetCommand(activeRunnerPreset, fullWorkerCommand);
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

export function setRunnerPreset(preset) {
  activeRunnerPreset = preset;
  document.querySelectorAll('[data-action="select-runner-preset"]').forEach(el => {
    el.classList.toggle('active', el.dataset.preset === preset);
  });

  const descEl = document.getElementById('runner-preset-desc');
  if (descEl) {
    if (preset === 'cloud-shell') {
      descEl.textContent = 'Recommended for free gigabit cloud-to-cloud transfers via browser terminal';
    } else if (preset === 'docker') {
      descEl.textContent = 'Persistent detached container runner for Linux VPS or Docker host';
    } else if (preset === 'curl') {
      descEl.textContent = 'Minimal direct cURL script runner for raw bash environments';
    }
  }

  const openCsBtn = document.getElementById('btn-open-cloud-shell');
  if (openCsBtn) {
    openCsBtn.classList.toggle('hidden', preset !== 'cloud-shell');
  }

  updateCmdDisplay();
}

export const selectRunnerPreset = setRunnerPreset;

function generatePresetCommand(preset, rawCmd) {
  if (!rawCmd) return '';
  if (preset === 'cloud-shell' || preset === 'curl') {
    return rawCmd;
  }
  if (preset === 'docker') {
    const idMatch = rawCmd.match(/--id\s+([^\s|&]+)/);
    const epMatch = rawCmd.match(/--endpoint\s+([^\s|&]+)/);
    const tokMatch = rawCmd.match(/--token\s+([^\s|&]+)/);
    const tsMatch = rawCmd.match(/--tailscale-key\s+([^\s|&]+)/);

    const wid = idMatch ? idMatch[1] : 'worker-runner';
    const ep = epMatch ? epMatch[1] : 'http://localhost:8080';
    const tok = tokMatch ? tokMatch[1] : '';
    const ts = tsMatch ? tsMatch[1] : '';

    let cmd = `docker run -d --name ${wid} --restart=unless-stopped --network=host -v /dev/shm:/dev/shm ghcr.io/boredkevin/immiclone-worker:latest --id ${wid} --endpoint ${ep}`;
    if (tok) cmd += ` --token ${tok}`;
    if (ts) cmd += ` --tailscale-key ${ts}`;
    return cmd;
  }
  return rawCmd;
}

function updateCmdDisplay() {
  const displayEl = document.getElementById('worker-cmd-display');
  if (!displayEl) return;
  const cmd = generatePresetCommand(activeRunnerPreset, fullWorkerCommand);
  if (cmd) {
    displayEl.innerHTML = formatCommandHtml(cmd);
    displayEl.title = 'Hover over blurred keys to reveal. Click Copy Worker Command to copy to clipboard.';
  } else {
    displayEl.innerHTML = '<span style="color:var(--text-muted);">curl -sSL https://raw.githubusercontent.com/BoredKevin/immiclone/refs/heads/main/worker/worker-stable.sh | bash <em>(Click &ldquo;Copy Worker Command&rdquo; or &ldquo;New Session&rdquo; to launch)</em></span>';
    displayEl.title = 'Click Copy Worker Command or New Session to generate a runner session';
  }
}

export function updateDuplicationData(transactions, workers) {
  latestTransactions = transactions || [];
  latestWorkers = workers || [];

  const navCount = document.getElementById('nav-tx-count');
  if (navCount) navCount.textContent = latestTransactions.length;

  renderTransactions(latestTransactions, latestWorkers);
  renderWorkers(latestWorkers);
  updateStage3BackupCard(latestTransactions, latestWorkers);
  updateWorkerConnectionListener(latestWorkers);
}

function updateStage3BackupCard(transactions, workers) {
  const routeEl = document.getElementById('backup-active-route');
  const workerPill = document.getElementById('backup-worker-pill');
  const workerText = document.getElementById('backup-worker-text');

  if (routeEl) {
    const activeTx = transactions.find(t => t.status === 'RUNNING') || transactions[0];
    if (activeTx) {
      routeEl.textContent = `${activeTx.source} -> ${activeTx.dest}`;
    } else {
      routeEl.textContent = 'bkc: -> backup:crypt';
    }
  }

  const activeWorker = workers.find(w => w.status === 'RUNNING');
  const standbyWorker = workers.find(w => w.status === 'STANDBY');

  if (workerPill && workerText) {
    if (activeWorker) {
      workerPill.className = 'badge badge-running';
      workerPill.innerHTML = `<span class="status-dot dot-green dot-pulse"></span> Connected: ${escapeHtml(activeWorker.name || activeWorker.id)}`;
    } else if (standbyWorker) {
      workerPill.className = 'badge badge-running';
      workerPill.innerHTML = `<span class="status-dot dot-green"></span> Ready: ${escapeHtml(standbyWorker.name || standbyWorker.id)}`;
    } else {
      workerPill.className = 'badge badge-standby';
      workerPill.innerHTML = '<span class="status-dot dot-amber"></span> Waiting for Worker';
    }
  }
}

function updateWorkerConnectionListener(workers) {
  const listenerBar = document.getElementById('worker-connection-listener');
  const listenerDot = document.getElementById('worker-listener-dot');
  const listenerText = document.getElementById('worker-listener-text');
  if (!listenerBar) return;

  const connectedWorker = workers.find(w => w.status !== 'OFFLINE' || (w.last_seen_sec !== undefined && w.last_seen_sec < 10));
  if (connectedWorker) {
    listenerBar.classList.add('connected');
    if (listenerDot) listenerDot.className = 'status-dot dot-green';
    if (listenerText) {
      listenerText.innerHTML = `<strong>Worker Connected!</strong> (${escapeHtml(connectedWorker.name || connectedWorker.id)}) &mdash; You can close this window.`;
    }
  } else {
    listenerBar.classList.remove('connected');
    if (listenerDot) listenerDot.className = 'status-dot dot-amber dot-pulse';
    if (listenerText) listenerText.textContent = 'Listening for worker connection...';
  }
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
  }

  const standbyWorkers = workers.filter(w => w.status === 'STANDBY');

  // Reconcile cards in-place using declarative <template id="tpl-tx-card">
  reconcileList(container, filtered, 'tpl-tx-card', t => t.tx_id, (el, tx) => {
    const isRunning = tx.status === 'RUNNING';
    const isQueued = tx.status === 'QUEUED';
    const isInterrupted = tx.status === 'INTERRUPTED';
    const isPaused = tx.status === 'PAUSED';
    const isCompleted = tx.status === 'COMPLETED';
    const isCancelled = tx.status === 'CANCELLED';

    // Header & metadata
    bindText(el, 'title', tx.title || 'Duplication Transaction');
    bindText(el, 'route', `${tx.source} -> ${tx.dest}`);
    bindText(el, 'mode', (tx.mode || 'copy').toUpperCase());
    bindText(el, 'tx-id', tx.tx_id);
    bindText(el, 'worker-name', tx.assigned_worker || 'None');

    // Mutually exclusive human status badge
    const badgeEl = getBoundElement(el, 'status-badge');
    if (badgeEl) {
      if (isRunning) {
        badgeEl.className = 'badge badge-running';
        badgeEl.innerHTML = `<span class="status-dot dot-green dot-pulse"></span> Transferring (Lease #${tx.lease_id || 1})`;
      } else if (isQueued) {
        if (tx.assigned_worker) {
          badgeEl.className = 'badge badge-queued';
          badgeEl.innerHTML = '<span class="status-dot dot-amber"></span> Queued for Worker';
        } else {
          badgeEl.className = 'badge badge-standby';
          badgeEl.innerHTML = '<span class="status-dot dot-amber"></span> Waiting for Worker';
        }
      } else if (isInterrupted) {
        badgeEl.className = 'badge badge-interrupted';
        badgeEl.innerHTML = '<span class="status-dot dot-red"></span> Interrupted';
      } else if (isPaused) {
        badgeEl.className = 'badge badge-paused';
        badgeEl.innerHTML = '<span class="status-dot dot-gray"></span> Paused';
      } else if (isCompleted) {
        badgeEl.className = 'badge badge-completed';
        badgeEl.innerHTML = '<span class="status-dot dot-purple"></span> Completed';
      } else if (isCancelled) {
        badgeEl.className = 'badge badge-interrupted';
        badgeEl.innerHTML = '<span class="status-dot dot-red"></span> Cancelled';
      }
    }

    // Flags micro-pills
    populateFlagPills(getBoundElement(el, 'flags-container'), tx.rclone_flags);

    // Notes
    const notesWrap = getBoundElement(el, 'notes-wrap');
    if (notesWrap) {
      if (tx.notes) {
        notesWrap.className = '';
        notesWrap.innerHTML = `<span class="tx-meta-sep">&bull;</span> <span>Notes: ${escapeHtml(tx.notes)}</span>`;
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
    if (isRunning) fillClass += ' running shimmer';
    const fillEl = getBoundElement(el, 'progress-fill');
    if (fillEl) fillEl.className = `progress-fill ${fillClass}`;

    // Current file resolution (resolving state conflict so CANCELLED doesn't show Queued)
    let currentFileText = tx.current_file || 'Idle';
    if (isCancelled) currentFileText = 'Cancelled';
    else if (isCompleted) currentFileText = 'Finished';
    bindText(el, 'current-file', currentFileText);

    // Rule 1: Toggle action buttons directly in <template> via .hidden
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
  const container = document.getElementById('workers-container');
  if (!container) return;

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

  // Reconcile worker cards in-place using declarative <template id="tpl-worker-row">
  reconcileList(container, filtered, 'tpl-worker-row', w => w.id, (el, w) => {
    const isRunning = w.status === 'RUNNING';
    const isOffline = w.status === 'OFFLINE';

    // Status badge & dot
    const statusBadge = getBoundElement(el, 'status-badge');
    if (statusBadge) {
      if (isRunning) {
        statusBadge.className = 'badge badge-running';
        statusBadge.innerHTML = '<span class="status-dot dot-green dot-pulse"></span> RUNNING';
      } else if (isOffline) {
        statusBadge.className = 'badge badge-offline';
        statusBadge.innerHTML = '<span class="status-dot dot-red"></span> OFFLINE';
      } else {
        statusBadge.className = 'badge badge-standby';
        statusBadge.innerHTML = '<span class="status-dot dot-amber"></span> STANDBY';
      }
    }

    bindText(el, 'name', w.name || w.id);
    bindText(el, 'id', w.id);
    bindText(el, 'hostname', w.hostname || '-');
    bindText(el, 'notes', w.notes || 'None');

    // Semver badge
    const wVer = w.version || '1.1.0';
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

    // Live Heartbeat Indicator (seconds since ping + pulsing dot)
    const hbDot = getBoundElement(el, 'heartbeat-dot');
    const hbText = getBoundElement(el, 'heartbeat-text');
    const hbBadge = getBoundElement(el, 'heartbeat-badge');
    const relTime = formatRelativeTime(w.last_seen_sec);

    if (hbDot) {
      if (isOffline) {
        hbDot.className = 'status-dot dot-red';
      } else {
        hbDot.className = 'status-dot dot-green dot-pulse';
      }
    }

    if (hbText) {
      if (isOffline) {
        hbText.textContent = `Offline (${relTime})`;
      } else if (w.last_seen_sec < 4) {
        hbText.textContent = 'Live ping (just now)';
      } else {
        hbText.textContent = `Heartbeat (${w.last_seen_sec}s ago)`;
      }
    }

    if (hbBadge) {
      hbBadge.className = isOffline ? 'worker-heartbeat worker-heartbeat-offline' : 'worker-heartbeat worker-heartbeat-active';
    }

    // Assigned transaction route & mini progress bar
    const tx = latestTransactions.find(t => t.tx_id === w.current_tx);
    if (w.current_tx && tx) {
      bindText(el, 'tx-route', `${tx.source} -> ${tx.dest}`);
      bindText(el, 'tx-id', tx.tx_id);
      bindHidden(el, 'tx-progress-wrap', false);

      const txPct = tx.percentage || 0;
      const progressFill = getBoundElement(el, 'tx-progress-fill');
      if (progressFill) {
        progressFill.style.width = `${txPct}%`;
      }
      bindText(el, 'tx-pct', `${txPct}%`);
      bindText(el, 'tx-speed', tx.speed_human || '0 B/s');
      bindText(el, 'tx-eta', tx.eta_sec ? `${tx.eta_sec}s` : '-');
    } else {
      bindText(el, 'tx-route', isOffline ? 'Disconnected' : 'No active transaction (Standby)');
      bindText(el, 'tx-id', w.current_tx || '-');
      bindHidden(el, 'tx-progress-wrap', true);
    }

    // Token display with sensitive blur
    const tokDisplay = getBoundElement(el, 'token-display');
    if (tokDisplay) {
      const tokVal = w.token || '••••••••••••••••';
      tokDisplay.textContent = tokVal;
      tokDisplay.title = 'Hover to reveal token';
    }

    // Quick action button toggles
    bindHidden(el, 'btn-stop-worker', !isRunning);
  });
}

const STORAGE_KEY = 'immiclone_worker_cmd';

export function initWorkerCmdBar() {
  const saved = sessionStorage.getItem(STORAGE_KEY);
  if (saved) {
    fullWorkerCommand = saved;
  }
  updateCmdDisplay();
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
    updateCmdDisplay();
    return fullWorkerCommand;
  } catch (e) {
    fullWorkerCommand = 'curl -sSL https://raw.githubusercontent.com/BoredKevin/immiclone/refs/heads/main/worker/worker-stable.sh | bash';
    updateCmdDisplay();
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
  if (!fullWorkerCommand) {
    await regenerateWorkerCmd(false);
  }
  const cmd = generatePresetCommand(activeRunnerPreset, fullWorkerCommand) || document.getElementById('worker-cmd-display')?.innerText || '';
  if (!cmd) return;

  const ok = await copyToClipboard(cmd);
  if (ok) {
    if (targetBtn) {
      const orig = targetBtn.innerHTML;
      targetBtn.innerHTML = 'Copied!';
      setTimeout(() => { targetBtn.innerHTML = orig; }, 1800);
    }
  } else {
    alert('Could not copy command to clipboard.');
  }
}
