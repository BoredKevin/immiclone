/* ==========================================================================
   Storage & Pipeline Stages 1 & 2 Controller
   Manages Root SSD, VFS Cache, RAM-disk, and Authoritative Cloud Quotas
   ========================================================================== */

import { reconcileList, bindText, bindStyle, getBoundElement } from './dom.js';

export function updateStorageMatrix(storage, summary) {
  if (!storage) return;

  // 1. Stage 1: Local Root SSD & VFS Cache
  const localSsd = storage.local_ssd || (storage.local_host && storage.local_host.root_ssd);
  const stageCardLocal = document.getElementById('stage-card-local');
  const ssdWarningHint = document.getElementById('ssd-warning-hint');

  if (localSsd) {
    const elUsed = document.getElementById('ssd-used');
    const elTotal = document.getElementById('ssd-total');
    const elFree = document.getElementById('ssd-free');
    const elPct = document.getElementById('ssd-pct');
    const elBar = document.getElementById('ssd-bar');
    const elDiskBar = document.getElementById('stat-disk-bar');

    const pct = localSsd.percent_used || 0;
    if (elUsed) elUsed.textContent = localSsd.used || '0 GB';
    if (elTotal) elTotal.textContent = localSsd.total || '0 GB';
    if (elFree) elFree.textContent = localSsd.free || '0 GB';
    if (elPct) elPct.textContent = pct + '%';

    let fillClass = 'green';
    const isWarning = pct >= 90;
    if (isWarning) fillClass = 'red';
    else if (pct >= 75) fillClass = 'amber';

    if (elBar) {
      elBar.className = `progress-fill ${fillClass}`;
      elBar.style.width = Math.min(100, pct) + '%';
    }
    if (elDiskBar) {
      elDiskBar.className = `progress-fill ${fillClass}`;
      elDiskBar.style.width = Math.min(100, pct) + '%';
    }

    // Low Root Disk Space Warning State (>90% used)
    if (stageCardLocal) {
      stageCardLocal.classList.toggle('warning-state', isWarning);
    }
    if (ssdWarningHint) {
      ssdWarningHint.classList.toggle('hidden', !isWarning);
    }
  }

  // 2. VFS Cache (Calm Teal/Blue bar, never warning-red for normal LRU cache)
  const vfsUsed = document.getElementById('vfs-used');
  const vfsTotal = document.getElementById('vfs-total');
  const vfsPct = document.getElementById('vfs-pct');
  const vfsBar = document.getElementById('vfs-bar');
  const elCachedSize = document.getElementById('stat-cached-size');
  const elCachedPct = document.getElementById('stat-cached-pct');
  const elCachedCount = document.getElementById('stat-cached');

  if (summary) {
    if (elCachedSize) elCachedSize.textContent = summary.cached_size || '0 MB';
    if (elCachedPct) elCachedPct.textContent = (summary.cache_percent || 0) + '%';
    if (elCachedCount) elCachedCount.textContent = (summary.cached_files || 0).toLocaleString();

    if (vfsUsed) vfsUsed.textContent = summary.cached_size || '0 MB';
    if (vfsPct) vfsPct.textContent = (summary.cache_percent || 0) + '%';
    if (vfsBar) {
      vfsBar.className = 'progress-fill blue';
      vfsBar.style.width = Math.min(100, summary.cache_percent || 0) + '%';
    }
  }

  // 3. Volatile RAM-Disk (/dev/shm) - Automatically hidden if capacity is 0 GB
  const shm = (storage.local_host && storage.local_host.shm) || storage.shm;
  const shmContainer = document.getElementById('shm-container');
  if (shm) {
    const isZero = !shm.total || shm.total === '0 B' || shm.total === '0 GB' || shm.total === '0 MB' || shm.total === 0;
    if (shmContainer) {
      shmContainer.classList.toggle('hidden', isZero);
    }

    if (!isZero) {
      const elShmUsed = document.getElementById('shm-used');
      const elShmTotal = document.getElementById('shm-total');
      const elShmPct = document.getElementById('shm-pct');
      const elShmBar = document.getElementById('shm-bar');
      const elShmFree = document.getElementById('shm-free');
      if (elShmUsed) elShmUsed.textContent = shm.used || '0 B';
      if (elShmTotal) elShmTotal.textContent = shm.total || '0 B';
      if (elShmPct) elShmPct.textContent = (shm.percent_used || 0) + '%';
      if (elShmBar) elShmBar.style.width = Math.min(100, shm.percent_used || 0) + '%';
      if (elShmFree) elShmFree.textContent = shm.free || '0 B';
    }
  } else if (shmContainer) {
    shmContainer.classList.add('hidden');
  }

  // 4. Stage 2: Authoritative Cloud Quotas & Remotes
  updateCloudQuota(storage);
}

function updateCloudQuota(storage) {
  // Primary Cloud Drive (bkc:) readouts
  const primary = storage.primary_cloud || (storage.remotes && storage.remotes[0]);
  if (primary) {
    const cloudUsed = document.getElementById('cloud-used');
    const cloudTotal = document.getElementById('cloud-total');
    const cloudFree = document.getElementById('cloud-free');
    const cloudPct = document.getElementById('cloud-pct');
    const cloudBar = document.getElementById('cloud-bar');
    const cloudTrash = document.getElementById('cloud-trash');
    const cloudTitle = document.getElementById('cloud-title');

    const remoteName = primary.remote || primary.remote_name || 'bkc:';
    if (cloudTitle) {
      cloudTitle.textContent = `Main Cloud Drive (${remoteName})`;
    }
    if (cloudUsed) cloudUsed.textContent = primary.used || '0 GB';
    if (cloudTotal) cloudTotal.textContent = primary.total || '0 GB';
    if (cloudFree) cloudFree.textContent = primary.free || '0 GB';
    if (cloudPct) cloudPct.textContent = (primary.percent_used || 0) + '%';
    if (cloudBar) {
      const pct = primary.percent_used || 0;
      let barClass = 'purple';
      if (pct >= 90) barClass = 'red';
      else if (pct >= 75) barClass = 'amber';
      cloudBar.className = `progress-fill ${barClass}`;
      cloudBar.style.width = Math.min(100, pct) + '%';
    }
    if (cloudTrash) cloudTrash.textContent = primary.trashed || '0 GB';
  }

  // Secondary Remotes Grid (if present)
  renderRemotesGrid(storage);
}

function renderRemotesGrid(storage) {
  const container = document.getElementById('cloud-remotes-grid');
  if (!container) return;

  const remotesList = storage.remotes || [];
  const primaryFallback = document.getElementById('card-primary-cloud');

  if (remotesList.length > 0) {
    if (primaryFallback && primaryFallback.dataset.standalone === 'true') {
      primaryFallback.classList.add('hidden');
    }

    reconcileList(container, remotesList, 'tpl-remote-card', r => r.name, (el, r) => {
      const pct = r.percent_used || 0;
      let barClass = 'purple';
      if (pct >= 90) barClass = 'red';
      else if (pct >= 75) barClass = 'amber';

      bindText(el, 'remote-name', r.name);
      bindText(el, 'remote-type', r.type || 'Cloud');
      bindText(el, 'used', r.used || '0 B');
      bindText(el, 'total', r.total || 'Unlimited');
      bindText(el, 'pct', `${pct}%`);
      bindStyle(el, 'progress-bar', 'width', `${Math.min(100, pct)}%`);
      const barEl = getBoundElement(el, 'progress-bar');
      if (barEl) barEl.className = `progress-fill ${barClass}`;

      bindText(el, 'free', r.free || 'Unknown');
      const trashWrap = getBoundElement(el, 'trash-wrap');
      if (trashWrap) {
        trashWrap.classList.toggle('hidden', !r.trashed);
        bindText(el, 'trash', r.trashed || '0 B');
      }
    });
  }
}
