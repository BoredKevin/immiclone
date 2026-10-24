/* ==========================================================================
   Local Rclone Mount Controller (Tab 3)
   ========================================================================== */

import { reconcileList, bindText, bindStyle, getBoundElement } from './dom.js';

export function updateMountStats(rclone) {
  if (!rclone) return;

  const elSpeed = document.getElementById('stat-rc-speed');
  const elActive = document.getElementById('stat-rc-active');
  const elDone = document.getElementById('stat-rc-done');
  const elTotal = document.getElementById('stat-rc-total');

  if (elSpeed) {
    elSpeed.textContent = rclone.speed || '0 B/s';
    const isIdle = !rclone.speed || rclone.speed === '0 B/s' || rclone.speed === '0.0 B/s';
    elSpeed.style.color = isIdle ? 'var(--text-muted)' : 'var(--green-light)';
  }
  if (elActive) elActive.textContent = rclone.transfers_active || 0;
  if (elDone) elDone.textContent = rclone.transfers_done || 0;
  if (elTotal) elTotal.textContent = rclone.total_uploaded || '0 B';

  renderJobsTable(rclone.jobs || []);
}

export function renderJobsTable(jobs) {
  const tbody = document.getElementById('jobs-table-body');
  if (!tbody) return;

  const emptyRow = document.getElementById('jobs-empty-row');
  if (emptyRow) {
    emptyRow.classList.toggle('hidden', jobs && jobs.length > 0);
  }

  // Reconcile jobs table rows in-place using declarative <template id="tpl-job-row">
  reconcileList(tbody, jobs || [], 'tpl-job-row', j => j.name, (el, j, isNew) => {
    // Clean redundant double path prefix
    const cleanName = (j.name || '').replace(/^library\/library\//, '').replace(/^library\//, '');
    const pct = j.percentage || 0;
    const isFinalizing = pct >= 100;
    const progressLabel = isFinalizing ? 'Finalizing / Verifying...' : `${pct}%`;
    const fillClass = isFinalizing ? 'progress-fill finalizing' : (pct > 0 ? 'progress-fill green shimmer' : 'progress-fill green');
    const etaLabel = isFinalizing ? 'Commit' : (j.eta ? j.eta + 's' : '-');

    bindText(el, 'file-name', cleanName);
    bindText(el, 'progress-label', progressLabel);
    bindStyle(el, 'progress-label', 'color', isFinalizing ? 'var(--amber)' : 'var(--heading)');
    bindText(el, 'bytes-label', `${j.bytes || '0 B'} / ${j.size || '0 B'}`);
    bindStyle(el, 'progress-bar', 'width', `${pct}%`);
    const barEl = getBoundElement(el, 'progress-bar');
    if (barEl) barEl.className = fillClass;

    bindText(el, 'speed', isFinalizing ? '-' : (j.speed || '0 B/s'));
    bindText(el, 'transferred', j.bytes || '0 B');
    bindText(el, 'eta', etaLabel);
  });
}
