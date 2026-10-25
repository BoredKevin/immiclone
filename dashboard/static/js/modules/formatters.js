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

export function formatIsoRelativeTime(isoStr) {
  if (!isoStr) return '-';
  try {
    const ms = Date.now() - new Date(isoStr).getTime();
    if (isNaN(ms)) return '-';
    return formatRelativeTime(Math.max(0, Math.floor(ms / 1000)));
  } catch {
    return '-';
  }
}

export function getMediaIcon(filename) {
  const ext = (filename || '').split('.').pop().toLowerCase();
  if (['mov', 'mp4', 'mkv', 'avi', 'webm', 'm4v', '3gp'].includes(ext)) {
    return {
      type: 'video',
      iconClass: 'media-icon-video',
      svg: `<svg class="icon icon-sm" viewBox="0 0 24 24"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg>`
    };
  }
  if (['jpg', 'jpeg', 'png', 'heic', 'heif', 'webp', 'gif', 'dng', 'raw', 'cr2', 'nef', 'arw'].includes(ext)) {
    return {
      type: 'image',
      iconClass: 'media-icon-image',
      svg: `<svg class="icon icon-sm" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>`
    };
  }
  if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'].includes(ext)) {
    return {
      type: 'audio',
      iconClass: 'media-icon-audio',
      svg: `<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>`
    };
  }
  return {
    type: 'doc',
    iconClass: 'media-icon-doc',
    svg: `<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>`
  };
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
