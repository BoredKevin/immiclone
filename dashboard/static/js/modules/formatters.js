/* ==========================================================================
   Formatting & Security Sanitization Utilities
   ========================================================================== */

export function formatRelativeTime(seconds) {
  if (seconds === undefined || seconds === null || isNaN(seconds) || seconds < 0) return '-';
  if (seconds < 5) return 'Just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return m > 0 ? `${h}h ${m}m ago` : `${h}h ago`;
  }
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function formatCommandHtml(cmd) {
  if (!cmd) return '';
  return escapeHtml(cmd)
    .replace(/(--token\s+)([^\s|&]+)/g, '$1<span class="sensitive-blur" title="Hover to reveal token">$2</span>')
    .replace(/(--tailscale-key\s+)([^\s|&]+)/g, '$1<span class="sensitive-blur" title="Hover to reveal Tailscale key">$2</span>');
}

export function maskCommandSecret(cmd) {
  if (!cmd) return '';
  return formatCommandHtml(cmd);
}

/**
 * Safely populates CLI flags as micro-pills inside container without raw HTML string injection.
 */
export function populateFlagPills(container, flagsInput) {
  if (!container) return;
  container.replaceChildren(); // Efficiently clears previous nodes

  let flags = [];
  if (Array.isArray(flagsInput)) {
    flags = flagsInput;
  } else if (typeof flagsInput === 'string' && flagsInput.trim()) {
    flags = flagsInput.trim().split(/\s+/);
  }

  if (!flags || flags.length === 0) {
    const dash = document.createElement('span');
    dash.style.color = 'var(--text-dim)';
    dash.textContent = '-';
    container.appendChild(dash);
    return;
  }

  for (let i = 0; i < flags.length; i++) {
    const span = document.createElement('span');
    span.className = 'flag-pill';
    span.textContent = flags[i];
    container.appendChild(span);
  }
}
