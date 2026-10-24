/* ==========================================================================
   Media & Cache Catalog Controller (Tab 2)
   ========================================================================== */

import { reconcileList, bindText, bindStyle, getBoundElement } from './dom.js';
import * as api from './api.js';

let currentPage = 1;
const pageLimit = 50;
let currentFilter = 'all';
let currentSearch = '';
let searchDebounce = null;
let mediaFilesCache = [];
let mediaSortCol = 'path';
let mediaSortAsc = false;

export function updateMediaSummary(summary) {
  if (!summary) return;
  const elTotal = document.getElementById('stat-total');
  const elCached = document.getElementById('stat-cached');
  const elCloud = document.getElementById('stat-cloud');
  const elCachedSize = document.getElementById('stat-cached-size');
  const elCachedPct = document.getElementById('stat-cached-pct');
  const elCacheBar = document.getElementById('stat-cache-bar');
  const elDiskFree = document.getElementById('stat-disk-free');

  if (elTotal) elTotal.textContent = (summary.total_files || 0).toLocaleString();
  if (elCached) elCached.textContent = (summary.cached_files || 0).toLocaleString();
  if (elCloud) elCloud.textContent = (summary.cloud_files || 0).toLocaleString();
  if (elCachedSize) elCachedSize.textContent = summary.cached_size || '0 MB';
  if (elCachedPct) elCachedPct.textContent = (summary.cache_percent || 0) + '%';
  if (elCacheBar) elCacheBar.style.width = Math.min(100, summary.cache_percent || 0) + '%';
  if (elDiskFree) elDiskFree.textContent = summary.disk_free || '0 GB';
}

export async function loadMedia() {
  try {
    const data = await api.fetchMedia(currentPage, pageLimit, currentFilter, currentSearch);
    mediaFilesCache = data.files || [];
    renderMediaTable(mediaFilesCache);
    updatePagination(data.page, data.total_pages, data.total_files);
  } catch (e) {
    console.error('[Media] Error fetching media catalog:', e);
  }
}

export function renderMediaTable(files) {
  const tbody = document.getElementById('table-body');
  if (!tbody) return;

  const emptyRow = document.getElementById('table-empty-row');
  if (emptyRow) {
    emptyRow.classList.toggle('hidden', files && files.length > 0);
  }

  // Reconcile media rows in-place using declarative <template id="tpl-media-row">
  reconcileList(tbody, files || [], 'tpl-media-row', f => f.path, (el, f, isNew) => {
    const isCached = Boolean(f.cached);

    const dot = getBoundElement(el, 'status-dot');
    if (dot) {
      dot.className = isCached ? 'status-dot dot-green' : 'status-dot dot-gray';
    }
    bindText(el, 'status-text', isCached ? 'Local SSD' : 'Cloud Drive');
    bindText(el, 'path', f.path || '');
    bindText(el, 'size', f.size || '0 B');
    bindText(el, 'mtime', f.mtime || '-');
  });
}

export function sortMediaTable(col) {
  if (mediaSortCol === col) {
    mediaSortAsc = !mediaSortAsc;
  } else {
    mediaSortCol = col;
    mediaSortAsc = true;
  }

  ['status', 'path', 'size', 'mtime'].forEach(c => {
    const el = document.getElementById(`sort-icon-${c}`);
    if (el) {
      if (c === col) {
        el.textContent = mediaSortAsc ? '↑' : '↓';
        el.parentElement.classList.add('sorted');
      } else {
        el.textContent = '↕';
        el.parentElement.classList.remove('sorted');
      }
    }
  });

  if (!mediaFilesCache || mediaFilesCache.length === 0) return;

  mediaFilesCache.sort((a, b) => {
    let valA, valB;
    if (col === 'status') {
      valA = a.cached ? 1 : 0;
      valB = b.cached ? 1 : 0;
    } else if (col === 'size') {
      valA = a.size_bytes || 0;
      valB = b.size_bytes || 0;
    } else if (col === 'mtime') {
      valA = a.mtime || '';
      valB = b.mtime || '';
    } else {
      valA = a.path || '';
      valB = b.path || '';
    }

    if (valA < valB) return mediaSortAsc ? -1 : 1;
    if (valA > valB) return mediaSortAsc ? 1 : -1;
    return 0;
  });

  renderMediaTable(mediaFilesCache);
}

function updatePagination(page, totalPages, totalItems) {
  currentPage = page;
  const prevBtn = document.getElementById('btn-prev');
  const nextBtn = document.getElementById('btn-next');
  const display = document.getElementById('page-display');

  if (prevBtn) prevBtn.disabled = page <= 1;
  if (nextBtn) nextBtn.disabled = page >= totalPages;

  if (display) {
    if (totalItems === 0) {
      display.textContent = 'Showing 0 of 0 items';
    } else {
      const start = (page - 1) * pageLimit + 1;
      const end = Math.min(page * pageLimit, totalItems);
      display.textContent = `Showing ${start.toLocaleString()}–${end.toLocaleString()} of ${totalItems.toLocaleString()} items (Page ${page} of ${totalPages})`;
    }
  }
}

export function changePage(delta) {
  currentPage += delta;
  loadMedia();
}

export function setMediaFilter(type) {
  currentFilter = type;
  document.querySelectorAll('#content-media .btn-group .btn').forEach(b => {
    b.classList.toggle('active', b.dataset.filter === type);
  });
  currentPage = 1;
  loadMedia();
}

export function onSearchInput(val) {
  currentSearch = (val || '').trim();
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    currentPage = 1;
    loadMedia();
  }, 250);
}
