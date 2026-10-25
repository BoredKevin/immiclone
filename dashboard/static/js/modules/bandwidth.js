/* ==========================================================================
   ISP Bandwidth & Monthly Quota Controller
   Modular Provider Registry Frontend Controller
   ========================================================================== */

import * as api from './api.js';

let latestBandwidthData = null;

export function updateBandwidthTelemetry(bw) {
  if (!bw) return;
  latestBandwidthData = bw;

  const quota = bw.quota || {};
  const downtime = bw.downtime || {};

  // 1. Header Compact Status Pill
  const headerPill = document.getElementById('header-bw-pill');
  const headerDot = document.getElementById('header-bw-dot');
  const headerText = document.getElementById('header-bw-text');

  if (headerText) {
    if (bw.online) {
      headerText.textContent = `${quota.remaining_str || '0 B'} (${quota.remaining_pct || 0}%) • ${bw.plan_speed_str || '100 Mbps'}`;
    } else {
      headerText.textContent = bw.error_message || 'Offline';
    }
  }

  if (headerDot) {
    if (!bw.online) {
      headerDot.className = 'status-dot dot-red';
    } else if (quota.remaining_pct <= 10) {
      headerDot.className = 'status-dot dot-red dot-pulse';
    } else if (quota.remaining_pct <= 20) {
      headerDot.className = 'status-dot dot-amber';
    } else {
      headerDot.className = 'status-dot dot-green';
    }
  }

  // 2. Bandwidth Card: Plan Badge & Status
  const planSpeedText = document.getElementById('bw-plan-speed-text');
  const statusBadge = document.getElementById('bw-status-badge');
  const statusDot = document.getElementById('bw-status-dot');
  const statusText = document.getElementById('bw-status-text');

  if (planSpeedText) {
    planSpeedText.textContent = `${bw.provider_name || 'ISP'} • ${bw.plan_speed_str || '100 Mbps'}`;
  }

  if (statusText) {
    if (!bw.online) {
      statusText.textContent = 'Offline';
      if (statusBadge) statusBadge.className = 'badge badge-interrupted';
      if (statusDot) statusDot.className = 'status-dot dot-red';
    } else if (quota.remaining_pct <= 20) {
      statusText.textContent = 'FUP Warning';
      if (statusBadge) statusBadge.className = 'badge badge-standby';
      if (statusDot) statusDot.className = 'status-dot dot-amber';
    } else {
      statusText.textContent = 'Online';
      if (statusBadge) statusBadge.className = 'badge badge-running';
      if (statusDot) statusDot.className = 'status-dot dot-green';
    }
  }

  // 3. Metric 1: Monthly Quota (FUP)
  const elQuotaRem = document.getElementById('bw-quota-remaining');
  const elQuotaTotal = document.getElementById('bw-quota-total');
  const elQuotaPct = document.getElementById('bw-quota-pct');
  const elQuotaBar = document.getElementById('bw-quota-bar');

  if (elQuotaRem) elQuotaRem.textContent = quota.remaining_str || '0 B';
  if (elQuotaTotal) elQuotaTotal.textContent = quota.limit_str || '0 B';
  if (elQuotaPct) elQuotaPct.textContent = `${quota.remaining_pct || 0}%`;

  if (elQuotaBar) {
    const remPct = Math.max(0, Math.min(100, quota.remaining_pct || 0));
    elQuotaBar.style.width = `${remPct}%`;
    if (remPct <= 10) {
      elQuotaBar.className = 'progress-fill red';
    } else if (remPct <= 20) {
      elQuotaBar.className = 'progress-fill amber';
    } else {
      elQuotaBar.className = 'progress-fill green';
    }
  }

  // 4. Metric 2: Live Line Saturation
  const elSatVal = document.getElementById('bw-saturation-val');
  const elSatPct = document.getElementById('bw-saturation-pct');
  const elPlanMbps = document.getElementById('bw-plan-mbps');
  const elSatBar = document.getElementById('bw-saturation-bar');

  if (elSatVal) elSatVal.textContent = bw.live_speed_str || '0 B/s';
  if (elSatPct) elSatPct.textContent = `${bw.saturation_pct || 0}%`;
  if (elPlanMbps) elPlanMbps.textContent = `${bw.plan_speed_mbps || 100} Mbps`;

  if (elSatBar) {
    const satPct = Math.max(0, Math.min(100, bw.saturation_pct || 0));
    elSatBar.style.width = `${satPct}%`;
    if (satPct >= 90) {
      elSatBar.className = 'progress-fill red';
    } else if (satPct >= 75) {
      elSatBar.className = 'progress-fill amber';
    } else {
      elSatBar.className = 'progress-fill blue';
    }
  }

  // 5. Details Row: Reset Cycle & Downtime Reason
  const elResetText = document.getElementById('bw-reset-text');
  if (elResetText) {
    const days = quota.days_left !== undefined ? quota.days_left : 0;
    elResetText.textContent = `Resets in ${days} ${days === 1 ? 'day' : 'days'}`;
  }

  const elDowntimeReason = document.getElementById('bw-downtime-reason');
  const elDowntimeSub = document.getElementById('bw-downtime-sub');
  const elDowntimeDot = document.getElementById('bw-downtime-dot');
  const elDowntimeBadge = document.getElementById('bw-downtime-badge');

  const reason = downtime.reason || 'Normal';
  const sub = downtime.subtext || 'No downtime detected';

  if (elDowntimeReason) elDowntimeReason.textContent = reason;
  if (elDowntimeSub) elDowntimeSub.textContent = sub;

  if (elDowntimeDot) {
    if (reason.toLowerCase().includes('dying-gasp')) {
      elDowntimeDot.className = 'status-dot dot-amber';
      if (elDowntimeBadge) elDowntimeBadge.className = 'badge badge-standby';
    } else if (reason.toLowerCase().includes('los') || reason.toLowerCase().includes('cut') || reason.toLowerCase().includes('error')) {
      elDowntimeDot.className = 'status-dot dot-red';
      if (elDowntimeBadge) elDowntimeBadge.className = 'badge badge-interrupted';
    } else {
      elDowntimeDot.className = 'status-dot dot-green';
      if (elDowntimeBadge) elDowntimeBadge.className = 'badge badge-running';
    }
  }
}

// ==========================================================================
// Modal & Configuration Management
// ==========================================================================

export async function openBandwidthModal() {
  const modal = document.getElementById('modal-bandwidth');
  if (!modal) return;
  modal.style.display = 'flex';
  modal.classList.add('active');

  const resultBox = document.getElementById('bw-test-result');
  if (resultBox) resultBox.style.display = 'none';

  try {
    const res = await fetch('/api/v1/bandwidth/config');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    populateBandwidthModal(data);
  } catch (err) {
    console.error('[Bandwidth] Error loading config:', err);
  }
}

function populateBandwidthModal(payload) {
  const cfg = (payload && payload.config) || {};
  const activeProvider = cfg.active_provider || 'biznet';

  const select = document.getElementById('bw-provider-select');
  if (select) {
    select.value = activeProvider;
    toggleProviderFields(activeProvider);
  }

  // Populate Biznet
  const biznet = (cfg.providers && cfg.providers.biznet) || {};
  const idEl = document.getElementById('bw-biznet-id');
  const userEl = document.getElementById('bw-biznet-user');
  const passEl = document.getElementById('bw-biznet-pass');
  const bearerEl = document.getElementById('bw-biznet-bearer');
  const tokenEl = document.getElementById('bw-biznet-token');
  if (idEl) idEl.value = biznet.biznet_id || '';
  if (userEl) userEl.value = biznet.username || '';
  if (passEl) passEl.value = biznet.password || '';
  if (bearerEl) bearerEl.value = biznet.bearer_token || '';
  if (tokenEl) tokenEl.value = biznet.api_token || '';

  // Populate Manual
  const manual = (cfg.providers && cfg.providers.manual) || {};
  const spdEl = document.getElementById('bw-manual-speed');
  const limEl = document.getElementById('bw-manual-limit');
  const remEl = document.getElementById('bw-manual-rem');
  const rstEl = document.getElementById('bw-manual-reset-day');
  const rsnEl = document.getElementById('bw-manual-reason');
  const subEl = document.getElementById('bw-manual-sub');

  if (spdEl) spdEl.value = manual.plan_speed_mbps || 100;
  if (limEl) limEl.value = manual.monthly_quota_gb || 1000;
  if (remEl) remEl.value = manual.quota_remaining_gb || 450;
  if (rstEl) rstEl.value = manual.reset_day_of_month || 1;
  if (rsnEl) rsnEl.value = manual.last_downtime_reason || 'Dying-gasp';
  if (subEl) subEl.value = manual.last_downtime_sub || 'Power loss detected by OLT';

  // General
  const pollEl = document.getElementById('bw-poll-interval');
  const warnEl = document.getElementById('bw-warn-threshold');
  if (pollEl) pollEl.value = cfg.poll_interval_seconds || 300;
  if (warnEl) warnEl.value = cfg.warning_threshold_pct || 20;
}

export function toggleProviderFields(providerId) {
  const bizFields = document.getElementById('bw-fields-biznet');
  const manFields = document.getElementById('bw-fields-manual');

  if (bizFields) bizFields.style.display = providerId === 'biznet' ? 'block' : 'none';
  if (manFields) manFields.style.display = providerId === 'manual' ? 'block' : 'none';
}

export async function saveBandwidthConfig() {
  const select = document.getElementById('bw-provider-select');
  const activeProvider = select ? select.value : 'biznet';

  const pollEl = document.getElementById('bw-poll-interval');
  const warnEl = document.getElementById('bw-warn-threshold');

  const newConfig = {
    enabled: true,
    active_provider: activeProvider,
    poll_interval_seconds: parseInt(pollEl ? pollEl.value : 300, 10) || 300,
    warning_threshold_pct: parseFloat(warnEl ? warnEl.value : 20.0) || 20.0,
    critical_threshold_pct: 10.0,
    providers: {
      biznet: {
        biznet_id: (document.getElementById('bw-biznet-id')?.value || '').trim(),
        username: (document.getElementById('bw-biznet-user')?.value || '').trim(),
        password: (document.getElementById('bw-biznet-pass')?.value || '').trim(),
        bearer_token: (document.getElementById('bw-biznet-bearer')?.value || '').trim(),
        api_token: (document.getElementById('bw-biznet-token')?.value || '').trim()
      },
      manual: {
        plan_speed_mbps: parseFloat(document.getElementById('bw-manual-speed')?.value || 100.0),
        monthly_quota_gb: parseFloat(document.getElementById('bw-manual-limit')?.value || 1000.0),
        quota_remaining_gb: parseFloat(document.getElementById('bw-manual-rem')?.value || 450.0),
        reset_day_of_month: parseInt(document.getElementById('bw-manual-reset-day')?.value || 1, 10),
        last_downtime_reason: (document.getElementById('bw-manual-reason')?.value || 'Dying-gasp').trim(),
        last_downtime_sub: (document.getElementById('bw-manual-sub')?.value || 'Power loss detected by OLT').trim()
      }
    }
  };

  try {
    const res = await fetch('/api/v1/bandwidth/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newConfig)
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const modal = document.getElementById('modal-bandwidth');
    if (modal) {
      modal.style.display = 'none';
      modal.classList.remove('active');
    }
  } catch (err) {
    alert(`Failed to save bandwidth settings: ${err.message}`);
  }
}

export async function testBandwidthConnection() {
  const btn = document.getElementById('btn-test-bw');
  const resultBox = document.getElementById('bw-test-result');
  const statusEl = document.getElementById('bw-test-status');
  const latencyEl = document.getElementById('bw-test-latency');
  const msgEl = document.getElementById('bw-test-msg');

  if (resultBox) resultBox.style.display = 'block';
  if (statusEl) {
    statusEl.textContent = 'Testing connection...';
    statusEl.style.color = 'var(--text-muted)';
  }
  if (btn) btn.disabled = true;

  const select = document.getElementById('bw-provider-select');
  const activeProvider = select ? select.value : 'biznet';

  let creds = {};
  if (activeProvider === 'biznet') {
    creds = {
      biznet_id: (document.getElementById('bw-biznet-id')?.value || '').trim(),
      username: (document.getElementById('bw-biznet-user')?.value || '').trim(),
      password: (document.getElementById('bw-biznet-pass')?.value || '').trim(),
      bearer_token: (document.getElementById('bw-biznet-bearer')?.value || '').trim(),
      api_token: (document.getElementById('bw-biznet-token')?.value || '').trim()
    };
  } else if (activeProvider === 'manual') {
    creds = {
      plan_speed_mbps: parseFloat(document.getElementById('bw-manual-speed')?.value || 100.0),
      monthly_quota_gb: parseFloat(document.getElementById('bw-manual-limit')?.value || 1000.0),
      quota_remaining_gb: parseFloat(document.getElementById('bw-manual-rem')?.value || 450.0),
      reset_day_of_month: parseInt(document.getElementById('bw-manual-reset-day')?.value || 1, 10),
      last_downtime_reason: (document.getElementById('bw-manual-reason')?.value || 'Dying-gasp').trim(),
      last_downtime_sub: (document.getElementById('bw-manual-sub')?.value || 'Power loss detected by OLT').trim()
    };
  }

  try {
    const res = await fetch('/api/v1/bandwidth/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: activeProvider, credentials: creds })
    });
    const diag = await res.json();

    if (latencyEl) latencyEl.textContent = `${diag.latency_ms || 0}ms`;
    if (diag.success) {
      if (statusEl) {
        statusEl.textContent = `● Success: ${diag.provider_name || activeProvider} Reachable`;
        statusEl.style.color = 'var(--green-light)';
      }
      if (msgEl) {
        msgEl.textContent = `Plan: ${diag.plan_speed_mbps} Mbps | Quota: ${diag.quota_remaining_str} of ${diag.quota_limit_str} | Downtime: ${diag.last_downtime_reason}`;
      }
    } else {
      if (statusEl) {
        statusEl.textContent = `● Failed: ${diag.provider_name || activeProvider} Unreachable`;
        statusEl.style.color = 'var(--red-light)';
      }
      if (msgEl) {
        msgEl.textContent = diag.error_message || diag.last_downtime_sub || 'Connection failed';
      }
    }
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = '● Request Error';
      statusEl.style.color = 'var(--red-light)';
    }
    if (msgEl) msgEl.textContent = err.message;
  } finally {
    if (btn) btn.disabled = false;
  }
}
