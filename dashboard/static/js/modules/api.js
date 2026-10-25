/* ==========================================================================
   Centralized REST API Client (API v1)
   ========================================================================== */

const API_PREFIX = '/api/v1';

async function apiGet(endpoint) {
  const url = endpoint.startsWith('/') ? endpoint : `${API_PREFIX}/${endpoint}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`GET ${url} failed with status ${res.status}`);
  }
  return res.json();
}

async function apiPost(endpoint, payload = {}) {
  const url = endpoint.startsWith('/') ? endpoint : `${API_PREFIX}/${endpoint}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    throw new Error(`POST ${url} failed with status ${res.status}`);
  }
  return res.json();
}

// Version & Updates
export const fetchVersion = () => apiGet(`${API_PREFIX}/version`);
export const fetchUpdates = (force = false) => apiGet(`${API_PREFIX}/updates?force=${force}`);
export const triggerUpdateCheck = () => apiPost(`${API_PREFIX}/updates/check`);

// Settings
export const fetchSettings = () => apiGet(`${API_PREFIX}/settings`);
export const saveSettings = (payload) => apiPost(`${API_PREFIX}/settings`, payload);


// Tailscale
export const fetchTailscaleConfig = () => apiGet(`${API_PREFIX}/tailscale/config`);
export const saveTailscaleConfig = (payload) => apiPost(`${API_PREFIX}/tailscale/save`, payload);
export const deleteTailscaleKey = () => apiPost(`${API_PREFIX}/tailscale/delete`);
export const testTailscaleKey = () => apiPost(`${API_PREFIX}/tailscale/test`);

// Remotes
export const fetchRemotes = () => apiGet(`${API_PREFIX}/worker/remotes`);

// Transactions
export const fetchTransactions = () => apiGet(`${API_PREFIX}/tx/list`);
export const createTx = (payload) => apiPost(`${API_PREFIX}/tx/create`, payload);
export const updateTx = (payload) => apiPost(`${API_PREFIX}/tx/update`, payload);
export const assignTx = (txId, workerId) => apiPost(`${API_PREFIX}/tx/assign`, { tx_id: txId, worker_id: workerId });
export const pauseTx = (txId) => apiPost(`${API_PREFIX}/tx/pause`, { tx_id: txId });
export const cancelTx = (txId) => apiPost(`${API_PREFIX}/tx/cancel`, { tx_id: txId });
export const deleteTx = (txId) => apiPost(`${API_PREFIX}/tx/delete`, { tx_id: txId });
export const resetTxProgress = (txId) => apiPost(`${API_PREFIX}/tx/reset-progress`, { tx_id: txId });
export const requeueTx = (txId) => apiPost(`${API_PREFIX}/tx/requeue`, { tx_id: txId });
export const clearCompletedTx = () => apiPost(`${API_PREFIX}/tx/clear-completed`);

// Workers
export const fetchWorkers = () => apiGet(`${API_PREFIX}/workers`);
export const createWorkerSession = (includeTs, forceFresh = false) => apiPost(`${API_PREFIX}/worker/create-session`, { include_tailscale: includeTs, force_fresh: forceFresh });
export const createWorker = (payload) => apiPost(`${API_PREFIX}/worker/create`, payload);
export const updateWorker = (payload) => apiPost(`${API_PREFIX}/worker/update`, payload);
export const disconnectWorker = (wid) => apiPost(`${API_PREFIX}/worker/disconnect`, { worker_id: wid });
export const deleteWorker = (wid) => apiPost(`${API_PREFIX}/worker/delete`, { worker_id: wid });
export const refreshWorkerToken = (wid) => apiPost(`${API_PREFIX}/worker/refresh-token`, { worker_id: wid });
export const pruneOfflineWorkers = () => apiPost(`${API_PREFIX}/worker/prune-offline`);

// Media
export const fetchMedia = (page, limit, filter, q) =>
  apiGet(`${API_PREFIX}/media?page=${page}&limit=${limit}&filter=${encodeURIComponent(filter)}&q=${encodeURIComponent(q)}`);

// Rclone Mount Control
export const throttleMount = (rate) => apiPost(`${API_PREFIX}/rclone/throttle`, { rate });
