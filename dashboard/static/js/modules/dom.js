/* ==========================================================================
   Declarative DOM Engine & Keyed List Reconciler
   Implements WeakMap binding cache (Rule 2) & zero innerHTML blowout
   ========================================================================== */

const elementBindCache = new WeakMap();

/**
 * Returns a map of bindKey -> HTMLElement for rootEl, cached in a WeakMap.
 * Guarantees O(1) element lookup on 500ms SSE updates without querySelector traversal.
 */
export function getBoundElements(rootEl) {
  if (!rootEl) return {};
  let bindings = elementBindCache.get(rootEl);
  if (!bindings) {
    bindings = {};
    if (rootEl.dataset && rootEl.dataset.bind) {
      bindings[rootEl.dataset.bind] = rootEl;
    }
    const nodes = rootEl.querySelectorAll('[data-bind]');
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const key = node.dataset.bind;
      bindings[key] = node;
    }
    elementBindCache.set(rootEl, bindings);
  }
  return bindings;
}

export function getBoundElement(rootEl, bindKey) {
  return getBoundElements(rootEl)[bindKey] || null;
}

/**
 * Safe text binding helper (prevents redundant DOM touch and guarantees zero XSS).
 */
export function bindText(rootEl, bindKey, text) {
  const el = getBoundElement(rootEl, bindKey);
  const str = text !== undefined && text !== null ? String(text) : '';
  if (el && el.textContent !== str) {
    el.textContent = str;
  }
}

/**
 * Safe attribute binding helper.
 */
export function bindAttr(rootEl, bindKey, attr, val) {
  const el = getBoundElement(rootEl, bindKey);
  if (!el) return;
  const str = val !== undefined && val !== null ? String(val) : '';
  if (el.getAttribute(attr) !== str) {
    el.setAttribute(attr, str);
  }
}

/**
 * Safe style property binding helper.
 */
export function bindStyle(rootEl, bindKey, prop, val) {
  const el = getBoundElement(rootEl, bindKey);
  if (el && el.style[prop] !== val) {
    el.style[prop] = val;
  }
}

/**
 * Safe class toggle binding helper.
 */
export function bindClass(rootEl, bindKey, className, condition) {
  const el = getBoundElement(rootEl, bindKey);
  if (el) {
    el.classList.toggle(className, Boolean(condition));
  }
}

/**
 * Safe visibility binding helper via .hidden class.
 */
export function bindHidden(rootEl, bindKey, isHidden) {
  const el = getBoundElement(rootEl, bindKey);
  if (el) {
    el.classList.toggle('hidden', Boolean(isHidden));
  }
}

/**
 * Keyed List Reconciler:
 * Diffs an array of items against child nodes in container using an HTML5 <template>.
 * Preserves existing DOM nodes, form control focus (such as worker <select>), and text selection.
 */
export function reconcileList(container, items, templateId, keyFn, updateFn) {
  if (!container) return;
  const template = document.getElementById(templateId);
  if (!template) {
    console.error(`[DOM] Template #${templateId} not found in document.`);
    return;
  }

  // Map existing child nodes by data-key
  const existingMap = new Map();
  for (let i = 0; i < container.children.length; i++) {
    const child = container.children[i];
    if (child.dataset && child.dataset.key) {
      existingMap.set(child.dataset.key, child);
    }
  }

  const seenKeys = new Set();
  let prevSibling = null;

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const key = String(keyFn(item));
    seenKeys.add(key);

    let el = existingMap.get(key);
    let isNew = false;

    if (!el) {
      const frag = template.content.cloneNode(true);
      el = frag.firstElementChild;
      el.dataset.key = key;
      isNew = true;
    }

    // Patch element using updateFn
    updateFn(el, item, isNew);

    // Maintain stable DOM ordering without destroying nodes
    if (isNew) {
      if (prevSibling) {
        prevSibling.after(el);
      } else {
        container.prepend(el);
      }
    } else {
      const currentSibling = el.previousElementSibling;
      if (currentSibling !== prevSibling) {
        if (prevSibling) {
          prevSibling.after(el);
        } else {
          container.prepend(el);
        }
      }
    }
    prevSibling = el;
  }

  // Remove nodes that are no longer in items
  for (const [key, child] of existingMap.entries()) {
    if (!seenKeys.has(key)) {
      child.remove();
    }
  }
}
