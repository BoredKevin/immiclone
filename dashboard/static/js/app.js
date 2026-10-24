let currentTab = 'tx';
let currentPage = 1;
let pageLimit = 50;
let currentFilter = 'all';
let searchDebounce = null;
let latestData = { transactions: [], workers: [], tailscale: {} };
let currentTxFilter = 'all';
let currentWorkerFilter = 'all';

function switchNav(tab) {
  currentTab = tab;
  document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  const navBtn = document.getElementById(`tab-nav-${tab}`);
  const content = document.getElementById(`content-${tab}`);
  if (navBtn) navBtn.classList.add('active');
  if (content) content.classList.add('active');
  if (tab === 'media') loadMedia();
}

// --- SSE TELEMETRY STREAM ---
function startSSE() {
  const evtSource = new EventSource('/api/stream');
  evtSource.onmessage = function(e) {
    try {
      const data = JSON.parse(e.data);
      latestData = data;
      updateDashboard(data);
    } catch (err) {
      console.error('SSE JSON error:', err);
    }
  };
  evtSource.onerror = function() {
    console.warn('SSE disconnected, reconnecting...');
  };
}

function updateDashboard(data) {
  // 1. Tailscale Banner
  if (data.tailscale) {
    const tb = document.getElementById('ts-badge');
    const td = document.getElementById('ts-status-desc');
    if (data.tailscale.configured) {
      tb.className = 'badge badge-running';
      tb.innerText = `● Configured (${data.tailscale.mode.toUpperCase()})`;
      const keyLabel = data.tailscale.masked_key || data.tailscale.masked_api || 'Active';
      td.innerHTML = `Active key: <code>${keyLabel}</code> • Ephemeral: <strong>${data.tailscale.ephemeral ? 'Yes' : 'No'}</strong> • Auto-inject: <strong>${data.tailscale.auto_inject ? 'Enabled' : 'Disabled'}</strong>`;
    } else {
      tb.className = 'badge badge-interrupted';
      tb.innerText = '○ Not Configured';
      td.innerText = 'No Tailscale key saved. Ephemeral cloud workers will run without Tailscale proxy unless supplied.';
    }
  }

  // 2. Summary & Storage
  if (data.summary) {
    document.getElementById('stat-total').innerText = data.summary.total_files.toLocaleString();
    document.getElementById('stat-cached').innerText = data.summary.cached_files.toLocaleString();
    document.getElementById('stat-cloud').innerText = data.summary.cloud_files.toLocaleString();
    document.getElementById('stat-cached-size').innerText = data.summary.cached_size;
    document.getElementById('stat-cached-pct').innerText = data.summary.cache_percent + '%';
    document.getElementById('stat-cache-bar').style.width = Math.min(100, data.summary.cache_percent) + '%';
    document.getElementById('stat-disk-free').innerText = data.summary.disk_free;
  }

  if (data.storage) {
    const st = data.storage;
    if (st.local_ssd) {
      document.getElementById('ssd-used').innerText = st.local_ssd.used;
      document.getElementById('ssd-total').innerText = st.local_ssd.total;
      document.getElementById('ssd-free').innerText = st.local_ssd.free;
      document.getElementById('ssd-pct').innerText = st.local_ssd.percent_used + '%';
      document.getElementById('ssd-bar').style.width = st.local_ssd.percent_used + '%';
    }
    if (st.cloud_bkc) {
      document.getElementById('cloud-used').innerText = st.cloud_bkc.used;
      document.getElementById('cloud-total').innerText = st.cloud_bkc.total;
      document.getElementById('cloud-free').innerText = st.cloud_bkc.free;
      document.getElementById('cloud-pct').innerText = st.cloud_bkc.percent_used + '%';
      document.getElementById('cloud-bar').style.width = st.cloud_bkc.percent_used + '%';
      document.getElementById('cloud-trash').innerText = st.cloud_bkc.trashed;
    }
  }

  // 3. Local Rclone stats
  if (data.rclone) {
    document.getElementById('stat-rc-speed').innerText = data.rclone.speed;
    document.getElementById('stat-rc-active').innerText = data.rclone.transfers_active;
    document.getElementById('stat-rc-done').innerText = data.rclone.transfers_done;
    document.getElementById('stat-rc-total').innerText = data.rclone.total_uploaded;
    renderJobsTable(data.rclone.jobs || []);
  }

  // 4. Transactions List
  if (data.transactions) {
    document.getElementById('nav-tx-count').innerText = data.transactions.length;
    renderTransactions(data.transactions, data.workers || []);
  }

  // 5. Workers Pool
  if (data.workers) {
    renderWorkers(data.workers);
  }
}

// --- TRANSACTION CRUD & RENDERING ---
function setTxFilter(f) {
  currentTxFilter = f;
  document.querySelectorAll('.filter-chips .chip').forEach(c => {
    if (c.id.startsWith('tx-filter-')) c.classList.remove('active');
  });
  const el = document.getElementById(`tx-filter-${f}`);
  if (el) el.classList.add('active');
  if (latestData.transactions) renderTransactions(latestData.transactions, latestData.workers || []);
}

function renderTransactions(txList, workers) {
  const container = document.getElementById('transactions-container');
  
  const runningCount = txList.filter(t => t.status === 'RUNNING').length;
  const pausedCount = txList.filter(t => ['PAUSED', 'INTERRUPTED', 'QUEUED'].includes(t.status)).length;
  const completedCount = txList.filter(t => ['COMPLETED', 'CANCELLED'].includes(t.status)).length;

  document.getElementById('count-tx-all').innerText = txList.length;
  document.getElementById('count-tx-running').innerText = runningCount;
  document.getElementById('count-tx-paused').innerText = pausedCount;
  document.getElementById('count-tx-completed').innerText = completedCount;

  let filtered = txList;
  if (currentTxFilter === 'running') filtered = txList.filter(t => t.status === 'RUNNING');
  else if (currentTxFilter === 'paused') filtered = txList.filter(t => ['PAUSED', 'INTERRUPTED', 'QUEUED'].includes(t.status));
  else if (currentTxFilter === 'completed') filtered = txList.filter(t => ['COMPLETED', 'CANCELLED'].includes(t.status));

  if (!filtered || filtered.length === 0) {
    container.innerHTML = `<div class="empty-state">No transactions matching filter '${currentTxFilter}'.</div>`;
    return;
  }

  const standbyWorkers = workers.filter(w => w.status === 'STANDBY');

  container.innerHTML = filtered.map(tx => {
    let statusBadge = '';
    let fillClass = 'green';
    if (tx.status === 'RUNNING') {
      statusBadge = `<span class="badge badge-running">● RUNNING (Lease #${tx.lease_id || 1})</span>`;
      fillClass = 'green';
    } else if (tx.status === 'INTERRUPTED') {
      statusBadge = `<span class="badge badge-interrupted">⚠️ INTERRUPTED (Resume Ready)</span>`;
      fillClass = 'red';
    } else if (tx.status === 'PAUSED') {
      statusBadge = `<span class="badge badge-paused">⏸ PAUSED</span>`;
      fillClass = 'orange';
    } else if (tx.status === 'COMPLETED') {
      statusBadge = `<span class="badge badge-completed">✓ COMPLETED</span>`;
      fillClass = 'purple';
    } else if (tx.status === 'CANCELLED') {
      statusBadge = `<span class="badge badge-interrupted">⏹ CANCELLED</span>`;
      fillClass = 'red';
    } else {
      statusBadge = `<span class="badge badge-standby">QUEUED</span>`;
      fillClass = 'orange';
    }

    const pct = tx.percentage || 0;
    const speed = tx.speed_human || '0 B/s';
    const transferredGb = ((tx.bytes_transferred || 0) / (1024**3)).toFixed(2);
    const totalGb = ((tx.total_bytes || 0) / (1024**3)).toFixed(2);
    const curFile = tx.current_file || 'Idle';
    const flagsStr = Array.isArray(tx.rclone_flags) ? tx.rclone_flags.join(' ') : (tx.rclone_flags || '--size-only');

    // Dynamic Action buttons
    let actionsHtml = '';
    if (tx.status === 'RUNNING') {
      actionsHtml = `
        <button class="btn btn-sm" onclick="pauseTx('${tx.tx_id}')">⏸ Pause</button>
        <button class="btn btn-sm btn-danger" onclick="cancelTx('${tx.tx_id}')">⏹ Cancel</button>
      `;
    } else if (['QUEUED', 'INTERRUPTED', 'PAUSED'].includes(tx.status)) {
      const workerOptions = standbyWorkers.map(w => `<option value="${w.id}">${w.name || w.id} (${w.hostname})</option>`).join('');
      if (standbyWorkers.length > 0) {
        actionsHtml = `
          <select class="form-select" id="assign-sel-${tx.tx_id}" style="width:220px; padding:6px; font-size:12px;">
            ${workerOptions}
          </select>
          <button class="btn btn-sm btn-primary" onclick="assignTx('${tx.tx_id}')">▶ ${tx.status === 'QUEUED' ? 'Start' : 'Resume'} on Worker</button>
        `;
      } else {
        actionsHtml = `<span style="font-size:12px; color:var(--gray);">Connect a worker via one-liner to ${tx.status === 'QUEUED' ? 'start' : 'resume'}.</span>`;
      }
      actionsHtml += `
        <button class="btn btn-sm" onclick="openEditTxModal('${tx.tx_id}')">✏️ Edit</button>
        <button class="btn btn-sm" onclick="resetTxProgress('${tx.tx_id}')">🔄 Reset Progress</button>
        <button class="btn btn-sm btn-danger" onclick="deleteTx('${tx.tx_id}')">🗑️ Delete</button>
      `;
    } else {
      // Completed or Cancelled
      actionsHtml = `
        <button class="btn btn-sm" onclick="requeueTx('${tx.tx_id}')">🔄 Re-Queue</button>
        <button class="btn btn-sm" onclick="openEditTxModal('${tx.tx_id}')">✏️ Edit</button>
        <button class="btn btn-sm btn-danger" onclick="deleteTx('${tx.tx_id}')">🗑️ Delete</button>
      `;
    }

    return `
      <div class="tx-card">
        <div class="tx-header">
          <div>
            <div class="tx-title">
              <span>${tx.title || tx.tx_id}</span>
              <span class="tx-route">${tx.source} ➔ ${tx.dest}</span>
              <span class="badge" style="background:#21262d; border:1px solid var(--border); font-family:monospace;">${(tx.mode || 'copy').toUpperCase()}</span>
              ${statusBadge}
            </div>
            <div class="tx-meta">
              <span>ID: <code>${tx.tx_id}</code></span>
              <span>•</span>
              <span>Flags: <code style="color:var(--gray);">${flagsStr}</code></span>
              ${tx.notes ? `<span>• Notes: ${tx.notes}</span>` : ''}
            </div>
          </div>
          <div style="font-size:13px; color:var(--gray); text-align:right;">
            Worker: <strong style="color:var(--heading);">${tx.assigned_worker || 'None'}</strong>
          </div>
        </div>

        <div class="tx-details">
          <div>Progress: <strong style="color:var(--heading);">${pct}%</strong> (${transferredGb} GB / ${totalGb} GB)</div>
          <div>Speed: <strong style="color:var(--green-light);">${speed}</strong></div>
          <div>Files: <strong style="color:var(--heading);">${tx.files_transferred || 0} copied</strong> (${tx.files_checked || 0} checked)</div>
          <div>ETA: <strong style="color:var(--heading);">${tx.eta_sec ? tx.eta_sec + 's' : '-'}</strong></div>
        </div>

        <div class="progress-bar">
          <div class="progress-fill ${fillClass}" style="width: ${pct}%"></div>
        </div>
        <div style="font-size:12px; color:var(--gray); margin-top:6px; font-family:monospace; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          Active: ${curFile}
        </div>

        <div class="tx-actions">
          ${actionsHtml}
        </div>
      </div>
    `;
  }).join('');
}

// --- WORKERS CRUD & RENDERING ---
function setWorkerFilter(f) {
  currentWorkerFilter = f;
  document.querySelectorAll('.filter-chips .chip').forEach(c => {
    if (c.id.startsWith('w-filter-')) c.classList.remove('active');
  });
  const el = document.getElementById(`w-filter-${f}`);
  if (el) el.classList.add('active');
  if (latestData.workers) renderWorkers(latestData.workers);
}

function renderWorkers(workers) {
  const tbody = document.getElementById('workers-table-body');
  
  const activeCount = workers.filter(w => w.status !== 'OFFLINE').length;
  const offlineCount = workers.filter(w => w.status === 'OFFLINE').length;

  document.getElementById('count-w-all').innerText = workers.length;
  document.getElementById('count-w-active').innerText = activeCount;
  document.getElementById('count-w-offline').innerText = offlineCount;

  let filtered = workers;
  if (currentWorkerFilter === 'active') filtered = workers.filter(w => w.status !== 'OFFLINE');
  else if (currentWorkerFilter === 'offline') filtered = workers.filter(w => w.status === 'OFFLINE');

  if (!filtered || filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No workers matching filter '${currentWorkerFilter}'.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(w => {
    let badge = '<span class="badge badge-standby">🟡 Standby</span>';
    if (w.status === 'RUNNING') badge = '<span class="badge badge-running">🟢 Running</span>';
    if (w.status === 'OFFLINE') badge = '<span class="badge badge-interrupted">🔴 Offline</span>';

    const lastSeen = w.status === 'OFFLINE' ? `<span style="color:var(--red); font-size:12px;">Offline (${w.last_seen_sec}s ago)</span>` : `<span style="color:var(--green-light); font-size:12px;">Active (${w.last_seen_sec}s ago)</span>`;

    return `
      <tr>
        <td>${badge}</td>
        <td>
          <strong style="color:var(--heading);">${w.name || w.id}</strong>
          <div style="font-family:monospace; font-size:11px; color:var(--gray);">${w.id}</div>
        </td>
        <td>${w.hostname}</td>
        <td>${w.current_tx ? `<code>${w.current_tx}</code>` : '<span style="color:var(--gray);">-</span>'}</td>
        <td>${lastSeen}</td>
        <td style="color:var(--gray); font-size:12px;">${w.notes || '-'}</td>
        <td style="text-align:right;">
          <button class="btn btn-sm" onclick="openEditWorkerModal('${w.id}')">✏️ Edit</button>
          ${w.status === 'RUNNING' ? `<button class="btn btn-sm btn-danger" onclick="disconnectWorker('${w.id}')">Stop</button>` : ''}
          ${w.status === 'OFFLINE' ? `
            <button class="btn btn-sm" onclick="resetWorker('${w.id}')">Standby</button>
            <button class="btn btn-sm btn-danger" onclick="deleteWorker('${w.id}')">🗑️</button>
          ` : ''}
        </td>
      </tr>
    `;
  }).join('');
}

function renderJobsTable(jobs) {
  const tbody = document.getElementById('jobs-table-body');
  if (!jobs || jobs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No active uploads right now. Cache is quiescent.</td></tr>';
    return;
  }
  tbody.innerHTML = jobs.map(j => `
    <tr>
      <td style="font-family:monospace; font-size:12px;">${j.name}</td>
      <td style="width: 220px;">
        <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
          <span>${j.percentage}%</span>
          <span>${j.bytes} / ${j.size}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill green" style="width:${j.percentage}%"></div></div>
      </td>
      <td style="color:var(--green-light); font-weight:600;">${j.speed}</td>
      <td>${j.bytes}</td>
      <td>${j.eta ? j.eta + 's' : '-'}</td>
    </tr>
  `).join('');
}

// --- API CALLS: TAILSCALE CRUD ---
function openTailscaleModal() {
  fetch('/api/tailscale/config')
    .then(r => r.json())
    .then(cfg => {
      document.getElementById('ts-mode').value = cfg.mode || 'auth_key';
      document.getElementById('ts-auth-key').value = '';
      document.getElementById('ts-auth-key').placeholder = cfg.masked_key || 'tskey-auth-...';
      document.getElementById('ts-tailnet').value = cfg.tailnet || '';
      document.getElementById('ts-api-key').value = '';
      document.getElementById('ts-api-key').placeholder = cfg.masked_api || 'tskey-api-...';
      document.getElementById('ts-auto-inject').checked = cfg.auto_inject !== false;
      document.getElementById('ts-ephemeral').checked = cfg.ephemeral !== false;
      toggleTsMode();
      document.getElementById('modal-tailscale').style.display = 'flex';
    });
}

function closeTailscaleModal() {
  document.getElementById('modal-tailscale').style.display = 'none';
}

function toggleTsMode() {
  const mode = document.getElementById('ts-mode').value;
  document.getElementById('ts-fields-auth').style.display = mode === 'auth_key' ? 'block' : 'none';
  document.getElementById('ts-fields-api').style.display = mode === 'api' ? 'block' : 'none';
  document.getElementById('ts-fields-oauth').style.display = mode === 'oauth' ? 'block' : 'none';
}

async function saveTailscaleConfig() {
  const mode = document.getElementById('ts-mode').value;
  const payload = {
    mode: mode,
    auth_key: document.getElementById('ts-auth-key').value.trim(),
    tailnet: document.getElementById('ts-tailnet').value.trim(),
    api_key: document.getElementById('ts-api-key').value.trim(),
    oauth_client_id: document.getElementById('ts-oauth-id').value.trim(),
    oauth_client_secret: document.getElementById('ts-oauth-secret').value.trim(),
    auto_inject: document.getElementById('ts-auto-inject').checked,
    ephemeral: document.getElementById('ts-ephemeral').checked
  };

  const res = await fetch('/api/tailscale/save', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (res.ok) {
    closeTailscaleModal();
    regenerateWorkerCmd();
  } else {
    alert('Failed to save Tailscale settings.');
  }
}

async function deleteTailscaleKey() {
  if (!confirm('Are you sure you want to clear the saved Tailscale credentials?')) return;
  await fetch('/api/tailscale/delete', { method: 'POST' });
  regenerateWorkerCmd();
}

async function testTailscaleKey() {
  const res = await fetch('/api/tailscale/test', { method: 'POST' });
  const data = await res.json();
  alert(`[Tailscale Test Result]\nStatus: ${data.status}\nMessage: ${data.message}`);
}

// --- API CALLS: TRANSACTION ACTIONS ---
function applyTxPreset() {
  const preset = document.getElementById('tx-preset').value;
  const titleEl = document.getElementById('tx-title');
  const srcEl = document.getElementById('tx-source');
  const dstEl = document.getElementById('tx-dest');
  const flagsEl = document.getElementById('tx-flags');
  const hintEl = document.getElementById('tx-flags-hint');

  if (preset === 'raw-gdrive') {
    titleEl.value = 'Raw Mirror: boredkevinmedia:crypt ➔ 1337quota:crypt';
    srcEl.value = 'boredkevinmedia:crypt';
    dstEl.value = '1337quota:crypt';
    flagsEl.value = '--transfers=8 --checkers=16 --fast-list --drive-server-side-across-configs';
    hintEl.innerText = 'Optimized for raw Google Drive-to-Google Drive replication (zero decryption, bit-for-bit).';
  } else if (preset === 'raw-terabox') {
    titleEl.value = 'Raw Mirror: boredkevinmedia:crypt ➔ tb:crypt';
    srcEl.value = 'boredkevinmedia:crypt';
    dstEl.value = 'tb:crypt';
    flagsEl.value = '--size-only --transfers=4 --checkers=8 --tpslimit=4';
    hintEl.innerText = 'Raw encrypted mirror directly to Terabox cloud.';
  } else if (preset === 'crypt-terabox') {
    titleEl.value = 'Decrypted Mirror: bkc:library ➔ tbc:library';
    srcEl.value = 'bkc:library';
    dstEl.value = 'tbc:library';
    flagsEl.value = '--size-only --transfers=4 --checkers=8 --tpslimit=4';
    hintEl.innerText = 'Decrypts in RAM and re-encrypts with Terabox crypt keys.';
  } else if (preset === 'crypt-1337quota') {
    titleEl.value = 'Decrypted Mirror: bkc:library ➔ 1qc:library';
    srcEl.value = 'bkc:library';
    dstEl.value = '1qc:library';
    flagsEl.value = '--transfers=8 --checkers=16 --fast-list --size-only';
    hintEl.innerText = 'Decrypts in RAM and re-encrypts into 1qc crypt remote.';
  }
}

async function loadRemotes() {
  try {
    const res = await fetch('/api/worker/remotes');
    const data = await res.json();
    const dl = document.getElementById('dest-remotes-list');
    if (dl) {
      dl.innerHTML = data.remotes.map(r => `<option value="${r}crypt"></option><option value="${r}library"></option>`).join('');
    }
  } catch (e) {
    console.error(e);
  }
}

function openNewTxModal() {
  loadRemotes();
  applyTxPreset();
  document.getElementById('modal-new-tx').style.display = 'flex';
}
function closeNewTxModal() {
  document.getElementById('modal-new-tx').style.display = 'none';
}

async function submitCreateTx() {
  const flagsInput = document.getElementById('tx-flags').value.trim();
  const payload = {
    title: document.getElementById('tx-title').value.trim(),
    source: document.getElementById('tx-source').value.trim(),
    dest: document.getElementById('tx-dest').value.trim(),
    mode: document.getElementById('tx-mode').value,
    priority: document.getElementById('tx-priority').value,
    rclone_flags: flagsInput ? flagsInput.split(/\s+/) : ['--size-only'],
    notes: document.getElementById('tx-notes').value.trim()
  };
  await fetch('/api/tx/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  closeNewTxModal();
}

function openEditTxModal(txId) {
  const tx = (latestData.transactions || []).find(t => t.tx_id === txId);
  if (!tx) return;
  document.getElementById('edit-tx-id').value = tx.tx_id;
  document.getElementById('edit-tx-title').value = tx.title || '';
  document.getElementById('edit-tx-source').value = tx.source || '';
  document.getElementById('edit-tx-dest').value = tx.dest || '';
  document.getElementById('edit-tx-mode').value = tx.mode || 'copy';
  document.getElementById('edit-tx-priority').value = tx.priority || 'normal';
  document.getElementById('edit-tx-flags').value = Array.isArray(tx.rclone_flags) ? tx.rclone_flags.join(' ') : (tx.rclone_flags || '');
  document.getElementById('edit-tx-notes').value = tx.notes || '';
  document.getElementById('modal-edit-tx').style.display = 'flex';
}

function closeEditTxModal() {
  document.getElementById('modal-edit-tx').style.display = 'none';
}

async function submitEditTx() {
  const txId = document.getElementById('edit-tx-id').value;
  const flagsInput = document.getElementById('edit-tx-flags').value.trim();
  const payload = {
    tx_id: txId,
    title: document.getElementById('edit-tx-title').value.trim(),
    source: document.getElementById('edit-tx-source').value.trim(),
    dest: document.getElementById('edit-tx-dest').value.trim(),
    mode: document.getElementById('edit-tx-mode').value,
    priority: document.getElementById('edit-tx-priority').value,
    rclone_flags: flagsInput ? flagsInput.split(/\s+/) : ['--size-only'],
    notes: document.getElementById('edit-tx-notes').value.trim()
  };
  await fetch('/api/tx/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  closeEditTxModal();
}

async function assignTx(txId) {
  const sel = document.getElementById(`assign-sel-${txId}`);
  if (!sel) return;
  await fetch('/api/tx/assign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx_id: txId, worker_id: sel.value })
  });
}

async function pauseTx(txId) {
  await fetch('/api/tx/pause', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx_id: txId })
  });
}

async function cancelTx(txId) {
  if (!confirm('Are you sure you want to cancel this duplication transaction?')) return;
  await fetch('/api/tx/cancel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx_id: txId })
  });
}

async function deleteTx(txId) {
  if (!confirm(`Permanently delete transaction ${txId}?`)) return;
  await fetch('/api/tx/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx_id: txId })
  });
}

async function resetTxProgress(txId) {
  if (!confirm(`Reset progress of transaction ${txId} to 0?`)) return;
  await fetch('/api/tx/reset-progress', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx_id: txId })
  });
}

async function requeueTx(txId) {
  await fetch('/api/tx/requeue', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tx_id: txId })
  });
}

async function clearCompletedTx() {
  if (!confirm('Clear all finished and cancelled duplication transactions?')) return;
  await fetch('/api/tx/clear-completed', { method: 'POST' });
}

// --- API CALLS: WORKERS ACTIONS ---
function openNewWorkerModal() {
  document.getElementById('worker-modal-title').innerText = 'Pre-Register Worker';
  document.getElementById('worker-modal-id').value = '';
  document.getElementById('worker-name').value = 'Cloud Shell Worker';
  document.getElementById('worker-notes').value = 'Google Cloud Console';
  document.getElementById('modal-worker').style.display = 'flex';
}

function openEditWorkerModal(wid) {
  const w = (latestData.workers || []).find(x => x.id === wid);
  if (!w) return;
  document.getElementById('worker-modal-title').innerText = `Edit Worker: ${wid}`;
  document.getElementById('worker-modal-id').value = wid;
  document.getElementById('worker-name').value = w.name || '';
  document.getElementById('worker-notes').value = w.notes || '';
  document.getElementById('modal-worker').style.display = 'flex';
}

function closeWorkerModal() {
  document.getElementById('modal-worker').style.display = 'none';
}

async function submitWorkerModal() {
  const wid = document.getElementById('worker-modal-id').value;
  const name = document.getElementById('worker-name').value.trim();
  const notes = document.getElementById('worker-notes').value.trim();

  if (wid) {
    await fetch('/api/worker/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ worker_id: wid, name: name, notes: notes })
    });
  } else {
    await fetch('/api/worker/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, notes: notes })
    });
  }
  closeWorkerModal();
  regenerateWorkerCmd();
}

async function disconnectWorker(wid) {
  if (!confirm(`Send STOP signal to worker ${wid}?`)) return;
  await fetch('/api/worker/disconnect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ worker_id: wid })
  });
}

async function resetWorker(wid) {
  await fetch('/api/worker/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ worker_id: wid })
  });
}

async function deleteWorker(wid) {
  if (!confirm(`Delete worker ${wid} from registry?`)) return;
  await fetch('/api/worker/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ worker_id: wid })
  });
}

async function pruneOfflineWorkers() {
  if (!confirm('Remove all offline workers from registry?')) return;
  await fetch('/api/worker/prune-offline', { method: 'POST' });
}

// --- WORKER COMMAND GENERATOR ---
async function regenerateWorkerCmd() {
  const includeTs = document.getElementById('chk-auto-ts').checked;
  try {
    const res = await fetch('/api/worker/create-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ include_tailscale: includeTs })
    });
    const data = await res.json();
    document.getElementById('worker-cmd-display').innerText = data.one_liner;
  } catch (e) {
    document.getElementById('worker-cmd-display').innerText = 'curl -sSL https://cdn.bkev.in/babel/worker.sh | bash';
  }
}

function copyWorkerCmd() {
  const cmd = document.getElementById('worker-cmd-display').innerText;
  navigator.clipboard.writeText(cmd).then(() => {
    alert('Worker one-liner copied to clipboard! Paste it into Google Cloud Shell.');
  }).catch(err => {
    alert('Could not auto-copy: ' + err);
  });
}

// --- MEDIA TAB FUNCTIONS ---
async function loadMedia() {
  const q = encodeURIComponent(document.getElementById('search').value.trim());
  const url = `/api/media?page=${currentPage}&limit=${pageLimit}&filter=${currentFilter}&q=${q}`;
  try {
    const res = await fetch(url);
    const data = await res.json();
    renderMediaTable(data.files);
    updatePagination(data.page, data.total_pages, data.total_files);
  } catch (e) {
    console.error('Error fetching media:', e);
  }
}

function renderMediaTable(files) {
  const tbody = document.getElementById('table-body');
  if (!files || files.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-state">No files matching criteria.</td></tr>';
    return;
  }
  tbody.innerHTML = files.map(f => {
    const badge = f.cached
      ? '<span class="badge badge-running">● Local SSD</span>'
      : '<span class="badge badge-standby">○ Cloud (bkc:)</span>';
    return `
      <tr>
        <td>${badge}</td>
        <td style="font-family:monospace; font-size:12px;">${f.path}</td>
        <td>${f.size}</td>
        <td style="color:var(--gray);">${f.mtime}</td>
      </tr>
    `;
  }).join('');
}

function updatePagination(page, totalPages, totalItems) {
  currentPage = page;
  document.getElementById('btn-prev').disabled = page <= 1;
  document.getElementById('btn-next').disabled = page >= totalPages;
  document.getElementById('page-display').innerText = `Page ${page} of ${totalPages} (${totalItems.toLocaleString()} items)`;
}

function changePage(delta) {
  currentPage += delta;
  loadMedia();
}

function setFilter(type) {
  currentFilter = type;
  document.querySelectorAll('#content-media .btn-group .btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById(`filter-${type}`);
  if (btn) btn.classList.add('active');
  currentPage = 1;
  loadMedia();
}

function onSearchInput() {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    currentPage = 1;
    loadMedia();
  }, 300);
}

// Init
window.addEventListener('DOMContentLoaded', () => {
  startSSE();
  regenerateWorkerCmd();
});
